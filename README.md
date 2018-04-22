# Robolove

A matchmaking website for people like you (or not, in which case you can go back from whence you came and never come back)

The database backend can be either mysql or postgresql, though mysql has been tested more thoroughly.

`example_config.json` is an example config, as the name suggests. Rename it to `config.json` after filling in the fields.
`wsgi.py` gives an example wsgi config. This usually lives somewhere like `/var/www`.
`ROBOLOVE_CONFIG_PATH` is the path to the config.json and should be set appropriately before the import in the wsgi.

Currently, skeleton.css is used for css. The avoidance of javascript is deliberate, for security and lightness reasons. Though feel free to contribute optional js anytime.
There are two "run modes" at this time: with an api server to which the webserver connects (see `myapi.py`), or with an adapter that mimics such an api. This is only because the host I use right now only allows running one webapp at a time.
