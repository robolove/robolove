import sys
import os

path = '.'
if path not in sys.path:
    sys.path.append(path)
os.environ["ROBOLOVE_CONFIG_PATH"] = path

from webserver import app as application
