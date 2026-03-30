from flask import render_template


class ComponentView:

    @staticmethod
    def render_index(components, category_groups, stats, search, selected_category,
                     sort_by, order, page, per_page, total, total_pages,
                     low_only=False, low_count=0):
        return render_template(
            "components/index.html",
            components=components, category_groups=category_groups, stats=stats,
            search=search, selected_category=selected_category,
            sort_by=sort_by, order=order,
            page=page, per_page=per_page, total=total, total_pages=total_pages,
            low_only=low_only, low_count=low_count,
        )

    @staticmethod
    def render_add(category_groups=None):
        return render_template("components/add.html", category_groups=category_groups or [])

    @staticmethod
    def render_import():
        return render_template("components/import.html")

    @staticmethod
    def render_detail(component, projects_using=None):
        import json as _json
        attrs = {}
        if component.attributes:
            try:
                attrs = _json.loads(component.attributes)
            except Exception:
                pass
        return render_template(
            "components/detail.html",
            component=component,
            projects_using=projects_using or [],
            attributes_dict=attrs,
        )

    @staticmethod
    def render_edit(component, category_groups=None):
        return render_template("components/edit.html", component=component,
                               category_groups=category_groups or [])

    @staticmethod
    def render_settings(current, stats=None):
        return render_template("components/settings.html",
                               current=current, stats=stats or {})
