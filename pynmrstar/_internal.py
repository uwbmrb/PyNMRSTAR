import decimal
import os
import sys
from datetime import date
from gzip import GzipFile
from io import StringIO, BytesIO
from typing import Dict, Union, IO
from urllib.request import urlopen

from . import entry as entry_mod
from . import schema as schema_mod
from . import utils

__version__: str = "3.0"


def _build_extension() -> bool:
    """ Try to compile the c extension. """
    import subprocess

    cur_dir = os.getcwd()
    try:
        src_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)))
        os.chdir(os.path.join(src_dir, '..', "c"))

        # Use the appropriate build command
        process = subprocess.Popen(['make', 'python3'], stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
        process.communicate()
        ret_code = process.poll()
        # The make command exited with a non-zero status
        if ret_code:
            return False

        # We were able to build the extension?
        return True
    except OSError:
        # There was an error going into the c dir
        return False
    finally:
        # Go back to the directory we were in before exiting
        os.chdir(cur_dir)


def _ensure_cnmrstar() -> bool:

    # See if we can use the fast tokenizer
    try:
        from . import cnmrstar

        if "version" not in dir(cnmrstar) or cnmrstar.version() < "2.2.8":
            print("Recompiling cnmrstar module due to API changes. You may experience a segmentation fault immediately "
                  "following this message but should have no issues the next time you run your script or this program.")
            _build_extension()
            sys.exit(0)

        return True

    except ImportError:

        # Check for the 'no c module' file before continuing
        if not os.path.isfile(os.path.join(os.path.dirname(os.path.realpath(__file__)), ".nocompile")):

            if _build_extension():
                try:
                    from . import cnmrstar
                    return True
                except ImportError:
                    return False

        return False


# noinspection PyDefaultArgument
def _get_comments(_comment_cache: Dict[str, Dict[str, str]] = {}) -> Dict[str, Dict[str, str]]:
    """ Loads the comments that should be placed in written files.

    The default argument is mutable on purpose, as it is used as a cache for memoization."""

    # Comment dictionary already exists
    if _comment_cache:
        return _comment_cache

    file_to_load = os.path.join(os.path.dirname(os.path.realpath(__file__)))
    file_to_load = os.path.join(file_to_load, "reference_files/comments.str")

    try:
        comment_entry = entry_mod.Entry.from_file(file_to_load)
    except IOError:
        # Load the comments from Github if we can't find them locally
        try:
            comment_url = "https://raw.githubusercontent.com/uwbmrb/PyNMRSTAR/v2/reference_files/comments.str"
            comment_entry = entry_mod.Entry.from_file(_interpret_file(comment_url))
        except Exception:
            # No comments will be printed
            return {}

    # Load the comments
    comment_records = comment_entry[0][0].get_tag(["category", "comment", "every_flag"])
    comment_map = {'N': False, 'Y': True}
    for comment in comment_records:
        if comment[1] != ".":
            _comment_cache[comment[0]] = {'comment': comment[1].rstrip() + "\n\n",
                                          'every_flag': comment_map[comment[2]]}

    return _comment_cache


def _json_serialize(obj: object) -> str:
    """JSON serializer for objects not serializable by default json code"""

    # Serialize datetime.date objects by calling str() on them
    if isinstance(obj, (date, decimal.Decimal)):
        return str(obj)
    raise TypeError("Type not serializable: %s" % type(obj))


def _tag_key(x, schema: 'schema_mod.Schema' = None) -> int:
    """ Helper function to figure out how to sort the tags."""

    try:
        return utils.get_schema(schema).schema_order.index(x)
    except ValueError:
        # Generate an arbitrary sort order for tags that aren't in the
        #  schema but make sure that they always come after tags in the
        #   schema
        return len(utils.get_schema(schema).schema_order) + abs(hash(x))


def _interpret_file(the_file: Union[str, IO]) -> StringIO:
    """Helper method returns some sort of object with a read() method.
    the_file could be a URL, a file location, a file object, or a
    gzipped version of any of the above."""

    if hasattr(the_file, 'read'):
        read_data: Union[bytes, str] = the_file.read()
        if type(read_data) == bytes:
            buffer: BytesIO = BytesIO(read_data)
        elif type(read_data, str):
            buffer = BytesIO(read_data.encode())
        else:
            raise IOError("What did your file object return when .read() was called on it?")
    elif isinstance(the_file, str):
        if the_file.startswith("http://") or the_file.startswith("https://") or the_file.startswith("ftp://"):
            with urlopen(the_file) as url_data:
                buffer = BytesIO(url_data.read())
        else:
            with open(the_file, 'rb') as read_file:
                buffer = BytesIO(read_file.read())
    else:
        raise ValueError("Cannot figure out how to interpret the file you passed.")

    # Decompress the buffer if we are looking at a gzipped file
    try:
        gzip_buffer = GzipFile(fileobj=buffer)
        gzip_buffer.readline()
        gzip_buffer.seek(0)
        buffer = BytesIO(gzip_buffer.read())
    # Apparently we are not looking at a gzipped file
    except (IOError, AttributeError, UnicodeDecodeError):
        pass

    buffer.seek(0)
    return StringIO(buffer.read().decode())