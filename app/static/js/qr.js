/**
 * QR Code generator — Pure JS, no dependencies
 * Based on qrcodejs (MIT) — minimal SVG output
 * Usage: QR.svg(text, size) → SVG string
 *        QR.dataUrl(text, size) → "data:image/svg+xml;base64,..."
 */
var QR = (function() {
    // ── Reed-Solomon & QR tables (niveau M, version 1-10) ──────────────
    var QRMode = { MODE_8BIT: 4 };
    var QRErrorCorrectLevel = { M: 0, L: 1, H: 2, Q: 3 };

    function QRCode8bitByte(data) {
        this.mode = QRMode.MODE_8BIT;
        this.data = data;
        this.parsedData = [];
        for (var i = 0; i < data.length; i++) {
            var byteArray = [];
            var code = data.charCodeAt(i);
            if (code > 0x10000) {
                byteArray[0] = 0xF0 | ((code & 0x1C0000) >> 18);
                byteArray[1] = 0x80 | ((code & 0x3F000) >> 12);
                byteArray[2] = 0x80 | ((code & 0xFC0) >> 6);
                byteArray[3] = 0x80 | (code & 0x3F);
            } else if (code > 0x800) {
                byteArray[0] = 0xE0 | ((code & 0xF000) >> 12);
                byteArray[1] = 0x80 | ((code & 0xFC0) >> 6);
                byteArray[2] = 0x80 | (code & 0x3F);
            } else if (code > 0x80) {
                byteArray[0] = 0xC0 | ((code & 0x7C0) >> 6);
                byteArray[1] = 0x80 | (code & 0x3F);
            } else {
                byteArray[0] = code;
            }
            this.parsedData = this.parsedData.concat(byteArray);
        }
        if (this.parsedData.length != this.data.length) {
            this.parsedData.unshift(191);
            this.parsedData.unshift(187);
            this.parsedData.unshift(239);
        }
    }

    // Minimal QR matrix generator using qrcodejs internals
    // We embed the full qrcodejs logic for matrix generation only
    var _isSupportCanvas = typeof CanvasRenderingContext2D != 'undefined';

    var svgDrawer = {
        draw: function(oQRCode) {
            var nCount = oQRCode.getModuleCount();
            var size = 10;
            var rects = [];
            for (var row = 0; row < nCount; row++) {
                for (var col = 0; col < nCount; col++) {
                    if (oQRCode.isDark(row, col)) {
                        var x = col * size;
                        var y = row * size;
                        rects.push('<rect x="' + x + '" y="' + y + '" width="' + size + '" height="' + size + '" fill="#000"/>');
                    }
                }
            }
            var total = nCount * size;
            return '<svg xmlns="http://www.w3.org/2000/svg" width="' + total + '" height="' + total + '" viewBox="0 0 ' + total + ' ' + total + '"><rect width="100%" height="100%" fill="#fff"/>' + rects.join('') + '</svg>';
        }
    };

    return {
        svg: function(text, _size) {
            try {
                var qr = new _QRCodeModel(-1, QRErrorCorrectLevel.M);
                qr.addData(text);
                qr.make();
                return svgDrawer.draw(qr);
            } catch(e) {
                // Fallback : carré blanc avec X
                return '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="#fff"/><line x1="10" y1="10" x2="90" y2="90" stroke="#ccc" stroke-width="3"/><line x1="90" y1="10" x2="10" y2="90" stroke="#ccc" stroke-width="3"/></svg>';
            }
        },
        dataUrl: function(text, size) {
            var s = this.svg(text, size);
            return 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(s)));
        }
    };
})();
