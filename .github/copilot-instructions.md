# Copilot instructions — ha-random-pools

This repository is a Home Assistant custom integration that exposes "pools" as sensors (random or queue-based selections of text lines and media files). Keep guidance concise and actionable so an AI coding agent can be immediately productive.

- **Big picture**: The integration provides two sensor sub-platforms:
  - `pools/sensor_lines.py` — exposes text pools from `.txt` files (one sensor per file).
  - `pools/sensor_media.py` — exposes media pools from folders (one sensor per folder).
  - `pools/sensor.py` simply delegates setup to both sub-platforms.
  - `pools/__init__.py` registers runtime services and exposes the `POOLS` registry (entity_id -> object).

- **Important files to read first**: `README.md`, `pools/__init__.py`, `pools/const.py`, `pools/sensor_lines.py`, `pools/sensor_media.py`, `pools/discover.py`, `pools/utils.py`.

- **Key project concepts & patterns**:
  - Global registry: `POOLS` in `pools/__init__.py` is the single place where sensor objects register themselves. When adding a new pool-like object, register it in `POOLS[entity_id] = obj` so services operate on it.
  - Service dispatch: services are defined in `pools/__init__.py` and call coroutine methods by name: `async_shuffle_and_push_state`, `async_force_reload_and_push_state`, `async_reset_and_push_attrs`.
  - IO offloading: blocking filesystem operations run in a threadpool via `hass.async_add_executor_job(...)` — follow this pattern for any file/dir reads to avoid blocking the HA event loop (see `discover.py` and `_load_file` / `_scan_dir`).
  - Autodiscovery: If no pools are specified in YAML, the integration auto-discovers files/folders using `scan_files` / `scan_media_folders` (see `sensor_lines.async_setup_platform` and `sensor_media.async_setup_platform`).
  - Config & validation: platform schemas use `voluptuous` and config keys are defined in `pools/const.py`. Use the same keys and validation style for new options.
  - Entity naming: suggested entity ids follow `sensor.pools_lines_{slug}` and `sensor.pools_media_{slug}`. Use `utils.slugify` (or `_slugify` in `sensor_media.py`) to derive stable suffixes.
  - URL serving rules: `sensor_media._build_url` implements `serve_from` semantics (`www` → `/local/...`, `media` → `media-source://...`, `component` → no web URL). Reference this when changing URL behavior.

- **Common changes an AI might make**:
  - Add a new config option: add constant in `pools/const.py`, update `PLATFORM_SCHEMA` in the relevant sensor module, and read the value in `async_setup_platform`.
  - Add a new service: implement async handler in `pools/__init__.py` and ensure it calls the expected coroutine name on pool objects (register with `hass.services.async_register(DOMAIN, ...)`).
  - Add new pool type: follow `LinesSensor` / `MediaSensor` structure — provide `async_added_to_hass`, register in `POOLS`, implement `async_*` methods used by services, and offload disk I/O with `async_add_executor_job`.

- **Project-specific conventions**:
  - Keep comments & logs English and concise (existing code follows this).
  - Limit automatic discovery to small, deterministic results (the code caps pools to the first 255 entries when creating entities).
  - Use `resolve_path(hass, rel)` helper to convert relative YAML paths to disk paths (see `utils.resolve_path`).
  - Use the existing attribute names from `pools/const.py` when exposing `extra_state_attributes`.

- **Examples (copy/paste friendly)**:
  - Register a new pool object in code: `from . import POOLS; POOLS[self.entity_id] = self`
  - Check for existence of files safely in executor: `await hass.async_add_executor_job(self._scan_dir)`
  - Use service name to call shuffle across pools: `hass.services.async_call('pools','shuffle', {'entity_id': ['sensor.pools_lines_hello']})`

- **Where to look for integration points**:
  - `pools/manifest.json` — metadata for the integration.
  - `pools/services.yaml` — the human-readable service definitions used by HA.
  - `pools/assets/` — sample `lines` and `media` example content used in autodiscovery and tests.

- **Notes / gotchas**:
  - File/folder paths in YAML are resolved relative to `hass.config.path(...)` unless absolute.
  - `no_repeat` uses a fixed-length deque of indices — manipulations must respect the deque API.
  - Keep any new disk scanning code in executor, and avoid long-running CPU-heavy tasks in the event loop.

If anything here is unclear or you want me to expand a specific section (e.g., examples for adding a new service or tests), tell me which part and I'll update the file.
