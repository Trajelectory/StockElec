import os
from flask import render_template, current_app
from ..models.settings import SettingsModel


class ComponentView:

    @staticmethod
    def render_index(components, category_groups, stats, search, selected_category,
                     sort_by, order, page, per_page, total, total_pages,
                     low_only=False, low_count=0, location_filter="", drawer_letters=None,
                     drawer_ateliers=None, all_ateliers_map=None,
                     smart_filter="", smart_counts=None):
        # ── Statuts KiCad pour tous les composants de la page ──────────
        # Calculé en batch ici pour ne pas le faire composant par composant
        # dans le template (appels glob répétés = lent).
        kicad_statuses = {}
        try:
            from ..services.kicad_jlc import get_component_kicad_status
            kicad_dir = os.path.join(current_app.instance_path, "kicad")
            if os.path.isdir(kicad_dir):
                for c in components:
                    lcsc = getattr(c, "lcsc_part_number", None) or ""
                    if lcsc:
                        kicad_statuses[lcsc] = get_component_kicad_status(lcsc, kicad_dir)
        except Exception:
            pass  # KiCad non configuré — pas grave, les icônes seront grises

        return render_template(
            "components/index.html",
            components=components, category_groups=category_groups, stats=stats,
            search=search, selected_category=selected_category,
            location_filter=location_filter, drawer_letters=drawer_letters or [],
            drawer_ateliers=drawer_ateliers or {}, all_ateliers_map=all_ateliers_map or {},
            sort_by=sort_by, order=order,
            page=page, per_page=per_page, total=total, total_pages=total_pages,
            low_only=low_only, low_count=low_count,
            kicad_statuses=kicad_statuses,
            smart_filter=smart_filter or "",
            smart_counts=smart_counts or {},
        )

    @staticmethod
    def render_add(category_groups=None):
        return render_template("components/add.html", category_groups=category_groups or [])

    @staticmethod
    def render_import():
        return render_template("components/import.html")

    @staticmethod
    def render_detail(component, projects_using=None):
        import json
        attrs = {}
        if component.attributes:
            try:
                attrs = json.loads(component.attributes)
            except Exception as e:
                logger.debug("Ignored: %s", e)
        from ..models.settings import SettingsModel
        from ..models.movement import MovementModel
        from ..services.kicad_jlc import get_component_kicad_status
        import os
        esp32_url    = SettingsModel.get("esp32_url", "").strip().rstrip("/")
        kicad_prefix = SettingsModel.get("kicad_prefix", "StockElec_").strip()
        history      = MovementModel.get_recent(limit=8, component_id=component.id)
        from flask import current_app
        kicad_dir    = os.path.join(current_app.instance_path, "kicad")
        kicad_status = get_component_kicad_status(
            component.lcsc_part_number or "", kicad_dir
        )
        return render_template(
            "components/detail.html",
            component=component,
            projects_using=projects_using or [],
            attributes_dict=attrs,
            esp32_url=esp32_url,
            history=history,
            kicad_status=kicad_status,
            kicad_prefix=kicad_prefix,
        )

    @staticmethod
    def render_edit(component, category_groups=None):
        return render_template("components/edit.html", component=component,
                               category_groups=category_groups or [])

    @staticmethod
    def render_settings(current, stats=None, config_plateaux=None):
        import os as _os

        def _fmt_size(path):
            """Taille lisible d'un fichier ou dossier."""
            if not _os.path.exists(path):
                return "—"
            if _os.path.isfile(path):
                size = _os.path.getsize(path)
            else:
                size = sum(
                    _os.path.getsize(_os.path.join(r, f))
                    for r, _, files in _os.walk(path)
                    for f in files
                )
            if size < 1024:       return f"{size} o"
            if size < 1024**2:   return f"{size/1024:.1f} Ko"
            return f"{size/1024**2:.1f} Mo"

        from flask import current_app
        inst = current_app.instance_path
        db_size   = _fmt_size(_os.path.join(inst, "stock.db"))
        img_size  = _fmt_size(_os.path.join(inst, "images"))
        proj_size = _fmt_size(_os.path.join(inst, "project_images"))

        # Total en bytes pour le résumé
        def _raw(path):
            if not _os.path.exists(path): return 0
            if _os.path.isfile(path): return _os.path.getsize(path)
            return sum(_os.path.getsize(_os.path.join(r, f))
                       for r, _, files in _os.walk(path) for f in files)

        total = (_raw(_os.path.join(inst, "stock.db")) +
                 _raw(_os.path.join(inst, "images")) +
                 _raw(_os.path.join(inst, "project_images")))
        if   total < 1024:    total_size = f"{total} o"
        elif total < 1024**2: total_size = f"{total/1024:.1f} Ko"
        else:                 total_size = f"{total/1024**2:.1f} Mo"

        # Couleurs LED par catégorie (settings ou défauts)
        from ..controllers.routes_led import LED_COLOR_DEFAULTS, LED_COLOR_SETTING_KEYS
        led_families = [
            ("Résistances",             "led_color_resistor",     "resistor",       "#f97316", "resistor*"),
            ("Condensateurs",           "led_color_capacitor",    "capacitor",      "#3b82f6", "capacitor*"),
            ("Inductances / Ferrites",  "led_color_inductor",     "inductor",       "#eab308", "inductor* / ferrite*"),
            ("Transistors / MOSFETs",   "led_color_transistor",   "transistor",     "#22c55e", "transistor* / mosfet*"),
            ("Diodes",                  "led_color_diode",        "diode",          "#ef4444", "diode*"),
            ("Optoélectronique",        "led_color_optoelectronic","optoelectronic", "#06b6d4", "optoelectronic* / display*"),
            ("LEDs / LED Drivers",      "led_color_led",          "led",            "#f0abfc", "led driver* / led *"),
            ("Amplificateurs / Comp.",  "led_color_amplifier",    "amplifier",      "#8b5cf6", "amplifier* / comparator*"),
            ("ICs / MCU / Logique",     "led_color_ic",           "ic",             "#a855f7", "integrated* / microcontroller* / logic* / interface* / embedded*"),
            ("Connecteurs / Sockets",   "led_color_connector",    "connector",      "#f8fafc", "connector* / socket* / header* / shunt*"),
            ("Interrupteurs / Boutons", "led_color_switch",       "switch",         "#94a3b8", "switch* / button*"),
            ("Clock / Timing / RTC",    "led_color_crystal",      "crystal",        "#67e8f9", "crystal* / oscillator* / clock* / real time*"),
            ("Fusibles / Protection",   "led_color_fuse",         "fuse",           "#fbbf24", "fuse* / protection*"),
            ("Capteurs",                "led_color_sensor",       "sensor",         "#34d399", "sensor*"),
            ("Alimentation / Régul.",   "led_color_power",        "power",          "#fb923c", "power* / voltage*"),
            ("Relais",                  "led_color_relay",        "relay",          "#c084fc", "relay* / transformer*"),
            ("Moteurs / Servos",        "led_color_motor",        "motor",          "#4ade80", "motor* / servo*"),
            ("RF / IoT / Antennes",     "led_color_rf",           "rf",             "#38bdf8", "rf* / iot* / communication* / antenna*"),
        ]
        # Résoudre la couleur courante (setting ou défaut)
        led_colors = []
        for label, setting_key, keyword, default_color, hint in led_families:
            saved = SettingsModel.get(setting_key, "").strip()
            current_color = saved if saved else default_color
            led_colors.append({
                "label":       label,
                "setting_key": setting_key,
                "color":       current_color,
                "default":     default_color,
                "hint":        hint,
            })

        # Plateaux de chaque atelier pour les sélecteurs dans settings
        from ..models.atelier import AtelierModel
        all_ateliers = AtelierModel.get_all()
        ateliers_plateaux = {}
        for _a in all_ateliers:
            _cfg = AtelierModel.get_rangement_config(_a["id"])
            ateliers_plateaux[_a["id"]] = _cfg.get("plateaux", [])

        return render_template("components/settings.html",
                               current=current,
                               stats=stats or {},
                               config_plateaux=config_plateaux or [],
                               led_colors=led_colors,
                               backup_db_size=db_size,
                               backup_img_size=img_size,
                               backup_proj_size=proj_size,
                               backup_total_size=total_size,
                           ateliers_plateaux=ateliers_plateaux)
