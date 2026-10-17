---
name: photocraft
description: "PhotoCraft tool map — open-source Photoshop clone driven over its local control server"
metadata:
  label: PhotoCraft
---

# PhotoCraft

PhotoCraft is not Adobe: use `photocraft_*`, never `photoshop_*`, when the user names
PhotoCraft. No COM, no JSX.

The first `photocraft_*` call (except `photocraft_status`) launches a controllable copy
if none is listening. A copy the user opened by hand is not controllable; that's
expected — the plugin opens its own window.

## Loop

1. `photocraft_inspect` (or `photocraft_status`)
2. `photocraft_commands(filter="layer")` to find ids and their `params` doc
3. `photocraft_run(command, params)` to change the document
4. `photocraft_inspect` / `photocraft_screenshot` to verify

`needsDocument: true` on a command means create or open a document first.

## Common commands

| Command | Params |
|---|---|
| `file.new` | `{"width":1920,"height":1080,"mode":"rgb","depth":8,"background":"white"}` |
| `layer.new.layer` | `{"name":"Ink"}` |
| `layer.select` | `{"layer":id}` or `{"name":"Background"}` |
| `layer.setProps` | `{"layer":id?,"name":…,"visible":…,"opacity":0..1,"blend":"Multiply"}` |
| `paint.stroke` | `{"points":[[x,y,pressure],…],"size":20,"color":"#ff0000"}` |
| `select.rect` | `{"x":0,"y":0,"width":100,"height":50,"mode":"add","ellipse":false}` |
| `layer.newAdjustmentLayer.hueSaturation` | `{"hue":30,"saturation":10}` |
| `edit.undo` | `{}` |

## Files

`photocraft_open(path)` / `photocraft_save(path)` only reach files under the PhotoCraft
root (the user's home folder, or `PHOTOCRAFT_ROOT`). Absolute paths under it are fine.
The extension picks the format: `.psd`, `.png`, `.jpg`, `.tga`… `file.open` / `file.save`
through `photocraft_run` are refused by PhotoCraft — use these two.

## UI

`photocraft_call(method, params)` sends any control method: `ui.inspect`, `ui.set {tool,
zoom, …}`, `ui.pointer {events:[{kind,x,y,pressure}], tool}` (document coordinates),
`ui.menu.invoke {id}`, `ui.dialog.set/confirm/cancel`, `ui.key {key}`.
