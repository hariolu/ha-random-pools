DOMAIN = "pools"

# Config keys
CONF_LINES_DIRECTORY = "lines_directory"
CONF_LINES_POOLS = "lines_pools"
CONF_MEDIA_DIRECTORY = "media_directory"
CONF_MEDIA_POOLS = "media_pools"
CONF_SELECTION_MODE = "selection_mode"      # random | queue
CONF_NO_REPEAT = "no_repeat"                # int >= 0
CONF_FALLBACK_TEXT = "fallback_text"
CONF_FALLBACK_URL = "fallback_url"
CONF_SERVE_FROM = "serve_from"              # component | www | media
CONF_INCLUDE = "include"
CONF_EXCLUDE = "exclude"
CONF_LINES_EXTS = "lines_extensions"
CONF_MEDIA_EXTS = "media_extensions"
CONF_MAX_LINES = "max_lines"
CONF_MAX_CHARS = "max_chars"

# Defaults
DEFAULT_LINES_DIRECTORY = "custom_components/pools/assets/lines"
DEFAULT_MEDIA_DIRECTORY = "custom_components/pools/assets/media"
DEFAULT_SELECTION_MODE = "random"
DEFAULT_NO_REPEAT = 1
DEFAULT_FALLBACK_TEXT = ""
DEFAULT_FALLBACK_URL = ""
DEFAULT_SERVE_FROM = "component"
DEFAULT_INCLUDE = []
DEFAULT_EXCLUDE = []
DEFAULT_LINES_EXTS = [".txt"]
DEFAULT_MEDIA_EXTS = [".mp3", ".ogg", ".wav", ".m4a", ".aac", ".opus", ".flac"]
DEFAULT_MAX_LINES = 255
DEFAULT_MAX_CHARS = 255

# Attributes
ATTR_FILE = "file"
ATTR_LINE_COUNT = "line_count"
ATTR_TRUNCATED_LINES = "truncated_lines"
ATTR_IGNORED_BLANK = "ignored_blank"
ATTR_LAST_INDEX = "last_index"
ATTR_FILE_MTIME = "file_mtime"

ATTR_SHUFFLE_COUNT = "shuffle_count"
ATTR_RELOAD_COUNT = "reload_count"
ATTR_LAST_SHUFFLE = "last_shuffle"
ATTR_LAST_RELOAD = "last_reload"

ATTR_DIR = "dir"
ATTR_FILE_COUNT = "file_count"
ATTR_LAST_FILE = "last_file"
ATTR_RELATIVE_URL = "relative_url"
ATTR_ABSOLUTE_URL = "absolute_url"
ATTR_DIR_MTIME = "dir_mtime"
