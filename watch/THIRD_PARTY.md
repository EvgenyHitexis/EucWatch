# Hardware source provenance

The application, behavior, rendering, transport and recovery code are original.
No community application menus, startup or coupled handler are retained.

`display.js` adapts fanoush's MIT-licensed B1/D native SPI/display driver from
[enaon/eucWatch, pinned revision 72744e4003405de5e6a754777929866ea7b065fc](https://github.com/enaon/eucWatch/blob/72744e4003405de5e6a754777929866ea7b065fc/v2/init/lcd_P8_16bit_rev.js).
The upstream file SHA-256 is
`9962be68dfe9976d42e65bdf0f3558b2b7c4dcf74af667775c23f4f328e4423f`.
The native binary, entry offsets, B1/D pin assignments, controller initialization
and palette transfer are preserved. The adaptation scopes the driver, removes
community application globals and settings access, fixes the framebuffer at
240×240×1 bpp (7,200 bytes), and uses a two-entry monochrome palette.

MIT License

Copyright (c) 2020 fanoush

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Touch, button, battery and charging

`hardware.js` is an original scoped adapter using the observed register/pin
contracts. Reference register values and gesture codes come from
[enaon's CST816 handler at the same pinned revision](https://github.com/enaon/eucWatch/blob/72744e4003405de5e6a754777929866ea7b065fc/Magic-testing/handler/handler_touch_816.js)
(SHA-256 `c8abe3fca1f773b9bc6d0b9318955f937f008e4abae43894628966390b5871fe`).
That source does not contain the display driver's MIT notice; this project does
not attribute that license to the touch source. Its application object,
callbacks and menus are not copied.

The installed contracts are documented in
[sanitized device evidence](../docs/research/p22-device-evidence.json) and
[backup/recovery research](../docs/research/p22-backup-recovery.md): touch reset
D10, deep sleep register E5, I2C D7/D6, interrupt D28, button supply D15/BTN1,
charger D19, active-high vibration D16 (idle 0), and battery analog input D31. Charger debounce
is 500 ms. Sampling reads 7.1×analogRead(D31), then disconnects its pin input
using the installed PIN_CNF register write. Percentage clamps at 3.5/4.19 V
and truncates the intervening linear percentage. These are installed driver
constants, not calibrated remaining energy or runtime predictions.

The measured E5/D10 configuration supersedes generic CST816 reset/sleep
settings. Physical gesture-origin reporting, display rotation, charging level,
and reset/deep-sleep behavior require actual-device acceptance.

## Direct BLE API

The direct adapter targets the
[Espruino RELEASE_2V14 Bluetooth implementation](https://github.com/espruino/Espruino/blob/RELEASE_2V14/libs/bluetooth/jswrap_bluetooth.c),
including its Promise-returning GATT disconnect. Explicit discovery selects an
FFE0/FFE1 source. There are no initialization, MTU or wheel-control writes in
this slice. Protocol provenance remains in
[Sherman L research](../docs/research/sherman-l-protocol.md).
