# CapCutAPI (vendored)

This folder is a copy of the draft-writing core of **CapCutAPI** by sun-guannan
(https://github.com/sun-guannan/CapCutAPI), licensed under the Apache License 2.0 (see `LICENSE`).
It includes `pyJianYingDraft`, the library that writes CapCut / Jianying draft files, originally by GuanYixuan.

Changes made for claude-video-skill:
- Only the parts needed to write a draft locally are kept: the `add_*` / `save_draft_impl` modules, `pyJianYingDraft`
  (without the Windows UI-automation controller), `settings`, and the draft templates.
- The Flask / MCP servers, tests, examples and the personal `config.json` are not included.
- `oss.py` imports `oss2` only when a draft is uploaded (not needed for local use).

It is used through `vdo/backends/capcut_backend.py`; it is not meant to be run on its own.
Re-copy from upstream to update it, then re-apply the two changes above.
