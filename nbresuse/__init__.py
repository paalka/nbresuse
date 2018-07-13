import os
import json
import psutil
from traitlets import Float, Int, Integer, default, TraitError
from traitlets.config import Configurable
from notebook.utils import url_path_join
from notebook.base.handlers import IPythonHandler

class ByteSpecification(Integer):
    """
    Allow easily specifying bytes in units of 1024 with suffixes
    Suffixes allowed are:
      - K -> Kilobyte
      - M -> Megabyte
      - G -> Gigabyte
      - T -> Terabyte
    """

    UNIT_SUFFIXES = {
        'K': 1024,
        'M': 1024 * 1024,
        'G': 1024 * 1024 * 1024,
        'T': 1024 * 1024 * 1024 * 1024,
    }

    # Default to allowing None as a value
    allow_none = True

    def validate(self, obj, value):
        """
        Validate that the passed in value is a valid memory specification
        It could either be a pure int, when it is taken as a byte value.
        If it has one of the suffixes, it is converted into the appropriate
        pure byte value.
        """
        if isinstance(value, (int, float)):
            return int(value)

        try:
            num = float(value[:-1])
        except ValueError:
            raise TraitError('{val} is not a valid memory specification. Must be an int or a string with suffix K, M, G, T'.format(val=value))
        suffix = value[-1]
        if suffix not in self.UNIT_SUFFIXES:
            raise TraitError('{val} is not a valid memory specification. Must be an int or a string with suffix K, M, G, T'.format(val=value))
        else:
            return int(float(num) * self.UNIT_SUFFIXES[suffix])


class MetricsHandler(IPythonHandler):
    def get(self):
        """
        Calculate and return current resource usage metrics
        """
        config = self.settings['nbresuse_display_config']
        cur_process = psutil.Process()
        all_processes = [cur_process] + cur_process.children(recursive=True)
        rss = sum([p.memory_info().rss for p in all_processes])

        limits = {}

        if config.mem_limit != 0:
            limits['memory'] = {
                'rss': config.mem_limit
            }
            if config.mem_warning_threshold != 0:
                limits['memory']['warn'] = (config.mem_limit - rss) < (config.mem_limit * config.mem_warning_threshold)
        metrics = {
            'rss': rss,
            'limits': limits,
        }
        self.write(json.dumps(metrics))


def _jupyter_server_extension_paths():
    """
    Set up the server extension for collecting metrics
    """
    return [{
        'module': 'nbresuse',
    }]

def _jupyter_nbextension_paths():
    """
    Set up the notebook extension for displaying metrics
    """
    return [{
        "section": "notebook",
        "dest": "nbresuse",
        "src": "static",
        "require": "nbresuse/main"
    }]

class ResourceUseDisplay(Configurable):
    """
    Holds server-side configuration for nbresuse
    """

    mem_warning_threshold = Float(
        0.1,
        help="""
        Warn user with flashing lights when memory usage is within this fraction
        memory limit.

        For example, if memory limit is 128MB, `mem_warning_threshold` is 0.1,
        we will start warning the user when they use (128 - (128 * 0.1)) MB.

        Set to 0 to disable warning.
        """,
        config=True
    )

    mem_limit = ByteSpecification(
        os.environ.get("MEM_LIMIT", 0),
        config=True,
        help="""
        Memory limit to display to the user, in bytes.

        Note that this does not actually limit the user's memory usage!

        Defaults to reading from the `MEM_LIMIT` environment variable. If
        set to 0, no memory limit is displayed.
        """
    )

def load_jupyter_server_extension(nbapp):
    """
    Called during notebook start
    """
    resuseconfig = ResourceUseDisplay(parent=nbapp)
    nbapp.web_app.settings['nbresuse_display_config'] = resuseconfig
    route_pattern = url_path_join(nbapp.web_app.settings['base_url'], '/metrics')
    nbapp.web_app.add_handlers('.*', [(route_pattern, MetricsHandler)])
