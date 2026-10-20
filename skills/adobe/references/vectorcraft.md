---
name: vectorcraft
description: "VectorCraft tool map — open-source Illustrator clone driven over its local control server"
metadata:
  label: VectorCraft
---

# VectorCraft

VectorCraft is not Adobe: use `vectorcraft_*`, never `illustrator_*`, when the user names
VectorCraft. No COM, no JSX.

The first `vectorcraft_*` call (except `vectorcraft_status`) launches a controllable copy
if none is listening. A copy the user opened by hand is not controllable; that's
expected — the plugin opens its own window.

## Loop

1. `vectorcraft_inspect` (or `vectorcraft_status`)
2. `vectorcraft_commands(filter="shape")` to find ids and their `params` doc
3. `vectorcraft_run(command, params)` to change the document
4. `vectorcraft_inspect` / `vectorcraft_screenshot` to verify

A params key the command doesn't take is refused before anything runs, with the nearest
key it does take: read the `params` doc from `vectorcraft_commands(filter=...)` first
(Drop Shadow in `effect.setParams` takes `x`, `y`, `blur`, `opacity`, `color`, not `xOffset`).
Without a filter `vectorcraft_commands` lists ids and labels only.

## Common commands

| Command | Params |
|---|---|
| `file.new` | `{"width":600,"height":400}` |
| `shape.rectangle` | `{"x":10,"y":10,"width":100,"height":50}` |
| `text.create` | `{"x":10,"y":60,"text":"Hello","size":30}` |
| `paint.setFill` | see `vectorcraft_commands(filter="paint.setFill")` |
| `select.all` / `object.group` / `object.align` | `{}` |
| `command.batch` | several commands in one undo step |

## Files

`vectorcraft_open(path)`, `vectorcraft_save(path)` and `vectorcraft_export(path, format,
use_artboards)` only reach files under the VectorCraft root (the user's home folder, or
`VECTORCRAFT_ROOT`). The extension picks the format: `.svg`, `.pdf`, `.png`, `.jpg`, `.webp`…
`use_artboards=true` writes one file per artboard. Missing folders are created, and both
tools answer only once the file is on disk (an error if VectorCraft failed to write it).

## UI

`vectorcraft_call(method, params)` sends any control method: `ui.inspect`, `ui.render
{artboard, scale, path}` (headless artboard PNG), `ui.menu.invoke {command, params}`,
`ui.pointer {events:[{kind,x,y}]}`, `ui.dialog.set/confirm/cancel`, `ui.key {key}`.
There is no `ui.dialog.close`: close an open dialog with `ui.dialog.cancel`.

`vectorcraft_screenshot` needs the window on screen; when it isn't, it returns a render of
the first artboard instead.
