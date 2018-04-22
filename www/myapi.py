PG_DB = False

if PG_DB:
    import psycopg2 as dblib
else:
    import MySQLdb as dblib

import hashlib
import binascii

from json import JSONDecodeError
import json as js

import sys
import os
errlog = sys.stderr

config_path = "."
if "ROBOLOVE_CONFIG_PATH" in os.environ:
    config_path = os.environ["ROBOLOVE_CONFIG_PATH"]

config = js.loads(open(config_path + "/config.json", "r").read())
assert("db" in config)
assert("host" in config)
assert("user" in config)
assert("password" in config)
assert("salt" in config)
assert("api" in config)

class DB:
    conn = None
    
    def __init__(self):
        self.connect()

    def connect(self):
        if PG_DB:
            self.conn = dblib.connect(dbname=config["db"], user=config["user"], password=config["password"], host=config["host"])    
        else:
            self.conn = dblib.connect(
                host=config["host"],
                user=config["user"],
                password=config["password"],
                db=config["db"])

    def execute(self, sql, params=None):
        try:
            cursor = self.conn.cursor()
            if params is not None:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
        except Exception:
            self.connect()
            cursor = self.conn.cursor()
            if params is not None:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
        return cursor

    def commit(self):
        self.conn.commit()

db = DB()

PREF_FEMALE = 0
PREF_BOTH = 1
PREF_MALE = 2

PREF_NAMES = ["female", "both", "male"]

def hash_passwd(passwd):
    return str(binascii.hexlify(hashlib.pbkdf2_hmac('sha256', bytes(passwd, 'utf8'), config["salt"].encode("utf-8"), 100000)))

def check_credentials(name, passwd):
    cur = db.execute("SELECT * FROM users WHERE uname = %s AND passwd = %s;", (name, hash_passwd(passwd)))
    try:
        valid = cur.fetchone()
        if valid is None:
            raise Exception
        return True
    except Exception:
        return False

def register(json_str):
    try:
        json = js.loads(json_str)
        if True:
            if "|" in json["name"]:
                return {"status": "error", "msg": "Invalid username"}

            cur = db.execute("SELECT COUNT(*) FROM users WHERE uname = %s;", (json["name"],))
            try:
                exists = cur.fetchone()
                if exists[0] == 0:
                    passwd = hash_passwd(json["passwd"])
                    cur = db.execute("INSERT INTO users (uname, passwd) VALUES (%s, %s)", (json["name"], passwd))
                    db.commit()
                    return {"status": "OK"}
                else:
                    return {"status": "error", "msg": "Username already registered"}
            except ProgrammingError:
                return {"status": "error", "msg": "Internal error, please report this issue to Robolove admin"}

    except Exception as e:
        print(e, file=errlog)
        cur = db.execute("ROLLBACK")
        db.commit()
        return {"status": "error", "msg": "Internal database error"}

def login(json_str):
    json = js.loads(json_str)
    if True:
        if "|" in json["name"]:
            return {"status": "error", "msg": "Invalid username"}

        if check_credentials(json["name"], json["passwd"]):
            return {"status": "OK"}
        else:
            return {"status": "error", "msg": "Username or password incorrect"}

def get_matches(which, full=False):
    """
    Get available matches for user `which`.
        full: Whether to only return matches where both parties agree
    """
    cur = db.execute("SELECT name1, name2 FROM matches WHERE name1 = %s AND hidden = 0;", (which,))
    matches = cur.fetchall()
    cur = db.execute("SELECT name1 FROM matches WHERE name2 = %s AND hidden = 0;", (which,))
    hopes_and_dreams = [c[0] for c in cur.fetchall()]

    matches_final = []
    for m in matches:
        if not full:
            matches_final.append(m[1])
        elif m[1] in hopes_and_dreams:
            matches_final.append(m[1])
    matches_final = list(set(matches_final))
    
    return matches_final

def get(json_str):
    json = js.loads(json_str)
    if True:
        what = json["what"] if "what" in json else "<MISSING>"
        which = json["which"] if "which" in json else "<MISSING>"

        if "start" in json and json["start"] is not None:
            start = json["start"]
        else:
            start = 0

        if "stop" in json and json["stop"] is not None:
            stop = str(json["stop"])
        else:
            #stop = "ALL"
            stop = str(2**31)

        if what == "pics":
            cur = db.execute("SELECT id, content FROM pics WHERE uname = %s LIMIT " + stop + " OFFSET %s;", (which, start))
            results = cur.fetchall()
            out = [{"id": i, "content": c} for i, c in results]
            return {"status": "OK", "ret": out}
        elif what == "user":
            if check_credentials(json["name"], json["passwd"]):
                cur = db.execute("SELECT name, descr, warn, male, pref, location, location_coords, discord FROM users WHERE uname = %s;", (which,))
                user = cur.fetchone()
                ret = {"uname": which, "name": user[0], "descr": user[1], "warn": user[2], "male": user[3], "pref": user[4], "location": user[5]}
                ret["location_coords"] = user[6]
                contact = (json["name"] == which) or (which in get_matches(json["name"], True))
                cur = db.execute("SELECT name2 FROM matches WHERE name1 = %s AND name2 = %s;", (which, json["name"]))
                maybeMatched = cur.fetchone()
                matched = maybeMatched is not None and (len(maybeMatched) == 1)
                if contact:
                    ret["discord"] = user[7]
                ret["matched"] = matched
                cur = db.execute("SELECT content FROM pics WHERE uname = %s LIMIT 1", (which,))
                pic = cur.fetchone()
                ret["pic"] = pic[0] if pic is not None else None

                if which == json["name"]:
                    all_matches = get_matches(json["name"], False)
                    ret["match_count"] = len(all_matches)

                return {"status": "OK", "ret": ret}
            else:
                return {"status": "error", "msg": "Missing user credentials"}
        elif what == "users":
            if check_credentials(json["name"], json["passwd"]):
                cur = db.execute("SELECT male, pref, location_coords FROM users WHERE uname = %s", (json["name"],))
                isMale, pref, coords = cur.fetchone()

                has_coords = False
                if coords is not None:
                    my_lat, my_lon = coords.split(',')
                    my_lat = float(my_lat)
                    my_lon = float(my_lon)
                    has_coords = True

                cond_str = ""
                if which == "true" and has_coords: # limit by location
                    cond_str = (" AND SQRT(POW((lat - %s), 2) + POW((lon - %s), 2)) < 2.0" % (my_lat, my_lon))

                cur = db.execute(("SELECT uname, name, descr, warn, male, pref, discord, location FROM (SELECT *, CAST(SUBSTRING_INDEX(location_coords, ',', 1) AS DECIMAL(10, 7)) AS lat,"
                    + "CAST(SUBSTRING_INDEX(location_coords, ',', -1) AS DECIMAL(10, 7)) AS lon FROM users) AS t WHERE (male=%s OR male=%s) AND (pref=%s OR pref=%s)" + cond_str)
                    + " AND uname <> %s LIMIT " + stop + " OFFSET %s;",
                        ((pref == PREF_MALE or pref == PREF_BOTH), (pref == PREF_MALE and pref != PREF_BOTH), PREF_MALE if isMale else PREF_FEMALE, PREF_BOTH, json["name"], start))
                matching_users = cur.fetchall()

                users = []
                if matching_users is not None and len(matching_users) > 0:
                    matches = get_matches(which, True)
                    matches_once = get_matches(json["name"], False)
                    for m in matching_users:
                        cur = db.execute("SELECT small FROM pics WHERE uname = %s LIMIT 1", (m[0],))
                        pic = cur.fetchone()
                        users.append({
                            "uname": m[0],
                            "name": m[1],
                            "descr": m[2],
                            "warn": m[3],
                            "male": m[4],
                            "pref": PREF_NAMES[m[5]],
                            "loc": m[7],
                            "pic": pic[0] if pic is not None else None,
                            "matched": False,
                            })
                        if m[0] in matches:
                            users[-1]["discord"] = m[6]
                        if m[0] in matches_once:
                            users[-1]["matched"] = True
                return {"status": "OK", "ret": users}
            else:
                return {"status": "error", "msg": "Missing user credentials"}
        elif what == "matches":
            matches = get_matches(which)
            users = []
            for m in matches:
                cur = db.execute("SELECT uname, name, descr, warn, male, pref, discord, location FROM users WHERE uname = %s", (m,))
                mm = cur.fetchone()
                cur = db.execute("SELECT small FROM pics WHERE uname = %s LIMIT 1", (m,))
                pic = cur.fetchone()
                users.append({
                    "uname": mm[0],
                    "name": mm[1],
                    "descr": mm[2],
                    "warn": mm[3],
                    "male": mm[4],
                    "pref": PREF_NAMES[mm[5]],
                    "loc": mm[7],
                    "pic": pic[0] if pic is not None else None,
                    })
            return {"status": "OK", "ret": users}
        elif what == "posts":
            thread = int(which)
            if thread < 0:
                cur = db.execute("SELECT thread, poster, title, content FROM posts WHERE id = thread ORDER BY id DESC")
            else:
                cur = db.execute("SELECT thread, poster, title, content FROM posts WHERE thread = %s ORDER BY id ASC", (thread,))
            posts = []
            db_data = cur.fetchall()
            for c in db_data:
                posts.append({"thread": c[0], "poster": c[1], "title": c[2], "content": c[3]})

                if thread < 0:
                    cur = db.execute("SELECT COUNT(*) FROM posts WHERE thread = %s", (c[0],))
                    cnt = cur.fetchone()
                    
                    if len(cnt) != 1:
                        return {"status": "error", "msg": "Failed to get post count"}
                    else:
                        posts[-1]["count"] = cnt[0]

            return {"status": "OK", "ret": posts}
        else:
            return {"status": "error", "msg": "Unknown request type: %s" % what}

def match(json_str):
    try:
        json = js.loads(json_str)
        if True:
            if check_credentials(json["name"], json["passwd"]):
                if json["action"] == "match":
                    cur = db.execute("INSERT INTO matches (name1, name2) VALUES (%s, %s);", (json["match"], json["name"]))
                elif json["action"] == "unmatch":
                    cur = db.execute("DELETE FROM matches WHERE name1 = %s AND name2 = %s;", (json["match"], json["name"]))
                elif json["action"] == "ignore":
                    cur = db.execute("UPDATE matches SET hidden = 1 WHERE name1 = %s AND name2 = %s;", (json["name"], json["match"]))
                db.commit()

                return {"status": "OK"}
            else:
                return {"status": "error", "msg": "Username or password incorrect"}
    except Exception as e:
        print(e, file=errlog)
        cur = db.execute("ROLLBACK")
        db.commit()
        return {"status": "error", "msg": "Internal database error"}

def report(json_str):
    try:
        json = js.loads(json_str)
        if True:
            if check_credentials(json["name"], json["passwd"]):
                cur = db.execute("INSERT INTO reports (reporter, reportee, reason) VALUES (%s, %s, %s)", (json["name"], json["target"], json["reason"]))
                db.commit()
                return {"status": "OK"}
            else:
                return {"status": "error", "msg": "Username or password incorrect"}
    except Exception as e:
        print(e, file=errlog)
        cur = db.execute("ROLLBACK")
        db.commit()
        return {"status": "error", "msg": "Internal database error"}

def update(json_str):
    try:
        json = js.loads(json_str)
        if True:
            if check_credentials(json["uname"], json["passwd"]):
                fields = []
                values = []
                for k, v in json.items():
                    if k in ["name", "discord", "new_passwd", "descr", "male", "pref", "location", "location_coords"]:
                        fields.append(k if k != "new_passwd" else "passwd")
                        values.append(v if k != "new_passwd" else hash_passwd(v))

                cur = db.execute("UPDATE users SET %s" % " = %s, ".join(fields) + " = %s WHERE uname = %s", (*values, json["uname"]))
                db.commit()
                return {"status": "OK"}
            else:
                return {"status": "error", "msg": "Username or password incorrect"}
    except Exception as e:
        print(e, file=errlog)
        cur = db.execute("ROLLBACK")
        db.commit()
        return {"status": "error", "msg": "Internal database error"}

def post(json_str):
    try:
        json = js.loads(json_str)
        if True:
            if check_credentials(json["name"], json["passwd"]):
                title = json["title"]
                thread = int(json["thread"]) if title == "" else -1
                cur = db.execute("INSERT INTO posts (poster, title, content, thread) VALUES (%s, %s, %s, %s)", (json["name"], json["title"], json["content"], thread))
                db.commit()

                id_ret = cur.lastrowid
                if thread < 0:
                    cur = db.execute("UPDATE posts SET thread = %s WHERE id = %s", (id_ret, id_ret))
                    db.commit()

                return {"status": "OK", "ret": id_ret}
            else:
                return {"status": "error", "msg": "Username or password incorrect"}
    except Exception as e:
        print(e, file=errlog)
        cur = db.execute("ROLLBACK")
        db.commit()
        return {"status": "error", "msg": "Internal database error"}

def update_pics(json_str):
    try:
        json = js.loads(json_str)
        if True:
            if check_credentials(json["name"], json["passwd"]):
                del_list = []
                add_list = []
                for p in json["pics"]:
                    if "id" in p:
                        if p["action"] == "del":
                           del_list.append(p["id"])
                    else:
                        add_list.append([p["content"], p["small"]])

                for pic in del_list:
                    cur = db.execute("DELETE FROM pics WHERE id = %s AND uname = %s", (pic, json["name"]))
                db.commit()
                for pic in add_list:
                    cur = db.execute("INSERT INTO pics (uname, content, small) VALUES (%s, %s, %s)", (json["name"], pic[0], pic[1]))
                db.commit()
                return {"status": "OK"}
            else:
                return {"status": "error", "msg": "Username or password incorrect"}
    except Exception as e:
        print(e, file=errlog)
        cur = db.execute("ROLLBACK")
        db.commit()
        return {"status": "error", "msg": "Internal database error"}

api_mapping = {
                    "get": get,
                    "update": update,
                    "update_pics": update_pics,
                    "register": register,
                    "login": login,
                    "match": match,
                    "report": report,
                    "post": post,
                }

if config["api"] == "":
    class Api:
        def __init__(self):
            self.functions = api_mapping

else:
    from flask import Flask

    app = Flask(__name__)
    app.config.from_object(__name__)
    for p, f in api_mapping.items():
        f = app.route("/" + p, methods=["POST"])(f)
        api_mapping[p] = f
