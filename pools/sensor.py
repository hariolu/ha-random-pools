# Thin orchestrator that exposes the 'sensor' platform for HA.
# It delegates to both Lines and Media sub-platforms.

from .sensor_lines import async_setup_platform as setup_lines
from .sensor_media import async_setup_platform as setup_media

async def async_setup_platform(hass, config, add_entities, discovery_info=None):
    # Set up both pools from the same YAML block:
    # - lines (files under lines_directory)
    # - media (folders under media_directory)
    await setup_lines(hass, config, add_entities, discovery_info)
    await setup_media(hass, config, add_entities, discovery_info)
