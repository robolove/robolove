import hashlib
import binascii

import html

import requests as real_requests
import json
import base64
import datetime
from json import JSONDecodeError
from flask import Flask, Markup, request, g, redirect, session
from jinja2 import Template
import jinja2
import PIL
from PIL import Image
from io import BytesIO

import markdown

import os
import sys
errlog = sys.stderr

import myapi

config_path = "."
if "ROBOLOVE_CONFIG_PATH" in os.environ:
    config_path = os.environ["ROBOLOVE_CONFIG_PATH"]

config = json.loads(open(config_path + "/config.json", "r").read())
assert("res_path" in config)
assert("session_secret" in config)
assert("api" in config)

PREF_NAMES = {"male": "Male", "both": "Both", "female": "Female"}
API_URL=config["api"]
NAME_API_URL="https://nominatim.openstreetmap.org"
WITH_ADAPTER=(API_URL == "")

env = jinja2.Environment(loader=jinja2.FileSystemLoader(config["res_path"]))

if WITH_ADAPTER:
    class ApiWrapper:
        def __init__(self, data):
            self.text = json.dumps(data)

    A = myapi.Api()

    class Requests:
        def post(self, url, data=None, headers=None):
            action = url.split("/")[-1]
            
            real_action = A.functions[action]
            return ApiWrapper(real_action(data))

        def get(self, url, data=None, headers=None):
            return real_requests.get(url, data=data, headers=headers)

    requests = Requests()

else:
    import requests

app = Flask(__name__)
app.config.from_object(__name__)
app.secret_key = config["session_secret"]

import os

@app.route("/", methods=["GET", "POST"])
def index():
    if "uname" in session:
        return redirect("/browse", code=303)

    template = env.get_template("html/index.html")
    return template.render()

@app.route("/logout", methods=["GET", "POST"])
def logout():
    session["uname"] = ""
    session["passwd"] = ""
    del session["uname"]
    del session["passwd"]

    return redirect("/", code=303)

@app.route("/error", methods=["GET", "POST"])
def error():
    extra = request.args["msg"] if "msg" in request.args else "(No Error)"
    template = env.get_template("html/error.html")
    return template.render(extra=extra)

@app.route("/user_info", methods=["GET", "POST"])
def user_info():
    if "uname" not in session:
        return redirect("/error?msg=%s" % "Please log in first", code=303)

    uname = session["uname"]
    passwd = session["passwd"]

    who = uname if (request.args is None or "who" not in request.args) else request.args["who"]
    self = (who == uname)

    info = get_user_info(uname, passwd, who)

    if info["status"] != "OK":
        return redirect("/error?msg=%s" % info["msg"], code=303)
    else:
        info["ret"]["myself"] = self
        info["ret"]["who"] = who
        info["ret"]["has_discord"] = "discord" in info["ret"]

        template = env.get_template("html/user_info.html")
        return template.render(info["ret"])

@app.route("/update_info", methods=["GET", "POST"])
def update_info():
    if "uname" not in session:
        return redirect("/error?msg=%s" % "Please log in first", code=303)

    if request.form["action"].strip().lower() == "cancel":
        return redirect("/browse", code=303)

    data = {}
    data["uname"] = session["uname"]
    data["new_passwd"] = session["passwd"] if ("passwd" not in request.form or len(request.form["passwd"]) == 0) else request.form["passwd"]
    for k in ["name", "discord", "descr", "sex", "pref", "location"]:
        if k in request.form:
            if k == 'pref':
                data[k] = int(request.form[k])
            if k == 'sex':
                data['male'] = request.form[k].strip().lower() == 'male'
            else:
                data[k] = html.escape(request.form[k])

    data["location_coords"] = "0,0"
    if "location" in data and len(data["location"]) > 0:
        name_to_coords_str = requests.get(NAME_API_URL + "/search?q=%s&format=json" % data["location"]).text
        name_to_coords = json.loads(name_to_coords_str)

        if(len(name_to_coords) > 0):
            data["location_coords"] = name_to_coords[0]["lat"] + "," + name_to_coords[0]["lon"]

    resp = json.loads(requests.post(API_URL + "/update", data=json.dumps(data), headers={'content-type': 'application/json'}).text)
    if resp["status"] == "OK":
        return redirect("/user_info", code=303)
    else:
        return redirect("/error?msg=%s" % resp["msg"], code=303)

def get_pics(uname, passwd, who):
    data = { "uname": uname, "passwd": passwd, "which": who, "what": "pics" }
    resp = json.loads(requests.post(API_URL + "/get", data=json.dumps(data), headers={'content-type': 'application/json'}).text)
    if resp["status"] == "OK":
        return resp["ret"]
    else:
        print("ERROR: failed to get pics for user", who, "--", resp["msg"], file=errlog)
        return []

@app.route("/pics", methods=["GET", "POST"])
def pics():
    if "uname" not in session:
        return redirect("/error?msg=%s" % "Please log in first", code=303)

    uname = session["uname"]
    who = uname if (request.form is None or "who" not in request.form or len(request.form["who"]) == 0) else request.form["who"]
    self = (who == uname)
    pics = get_pics(uname, session["passwd"], who)
    data = {"pics": pics, "myself": self, "who": who}
    
    template = env.get_template("html/pics.html")
    return template.render(data)

@app.route("/del_pics", methods=["GET", "POST"])
def del_pics():
    if "uname" not in session:
        return redirect("/error?msg=%s" % "Please log in first", code=303)

    data = {"pics": []}
    data["name"] = session["uname"]
    data["passwd"] = session["passwd"]
    for p in request.form.items():
        if p[0] not in ["action", "image", "pic"]:
            data["pics"].append({"id": p[0], "action": "del"})
    resp = json.loads(requests.post(API_URL + "/update_pics", data=json.dumps(data), headers={'content-type': 'application/json'}).text)
    if resp["status"] == "OK":
        return redirect("/pics", code=303)
    else:
        return redirect("/error?msg=%s" % resp["msg"], code=303)

@app.route("/add_pics", methods=["GET", "POST"])
def add_pics():
    if "uname" not in session:
        return redirect("/error?msg=%s" % "Please log in first", code=303)

    data = {"pics": []}
    data["name"] = session["uname"]
    data["passwd"] = session["passwd"]

    if "pic" in request.files:
        try:
            pic_obj = Image.open(request.files["pic"].stream)
            pic_io = BytesIO()
            pic_obj.save(pic_io, format="PNG")
            pic = pic_io.getvalue()
        except Exception:
            return redirect("/error?msg=%s" % "Only images allowed", code=303)

        if(float(len(pic)) / (1024*1024) > 2.):
            return redirect("/error?msg=%s" % "Image size too big (max: 2mb)", code=303)

        pic_small_obj = pic_obj.resize((480, int((480. / pic_obj.size[0]) * pic_obj.size[1])))
        pic_small_io = BytesIO()
        pic_small_obj.save(pic_small_io, format="PNG")
        pic_small = pic_small_io.getvalue()

        data["pics"].append({"content": base64.encodestring(pic).decode("utf-8"), "small": base64.encodestring(pic_small).decode("utf-8"), "action": "add"})
    resp = json.loads(requests.post(API_URL + "/update_pics", data=json.dumps(data), headers={'content-type': 'application/json'}).text)
    if resp["status"] == "OK":
        return redirect("/pics", code=303)
    else:
        return redirect("/error?msg=%s" % resp["msg"], code=303)

@app.route("/matches", methods=["GET", "POST"])
def matches():
    if "uname" not in session:
        return redirect("/error?msg=%s" % "Please log in first", code=303)

    uname = session["uname"]
    passwd = session["passwd"]

    start = int(request.args["s"]) if "s" in request.args else 0
    end = int(request.args["e"]) if "e" in request.args else 25
    next_start = end
    next_end = end + 25
    prev_start = max(0, start - 25)
    prev_end = max(start, 25)
    limit_loc = request.args["l"] if "l" in request.args else "true"

    try:
        resp = requests.post(API_URL + "/get", data=json.dumps({"name": uname, "passwd": passwd, "what": "matches", "which": uname}), headers={'content-type': 'application/json'})
        resp = json.loads(resp.text)
    except Exception as e:
        return redirect("/error?msg=%s" % "Failed to find matches", code=303)

    if resp["status"] != "OK":
        return redirect("/error?msg=%s" % resp["msg"], code=303)

    data = {}
    data["next_start"] = next_start
    data["next_end"] = next_end
    data["prev_start"] = prev_start
    data["prev_end"] = prev_end
    data["start"] = start
    data["end"] = end
    data["limit_loc"] = limit_loc
    data["here"] = "matches"

    for i, r in enumerate(resp["ret"]):
        resp["ret"][i]["sex"] = "M" if r["male"] else "F"
        resp["ret"][i]["prefer"] = PREF_NAMES[r["pref"]]
        if "descr" in resp["ret"][i]:
            resp["ret"][i]["descr"] = Markup(markdown.markdown(resp["ret"][i]["descr"]))

    data["people"] = resp["ret"]

    template = env.get_template("html/browse.html")
    return template.render(data)

@app.route("/match", methods=["GET", "POST"])
def match():
    if "uname" not in session:
        return redirect("/error?msg=%s" % "Please log in first", code=303)

    uname = session["uname"]
    passwd = session["passwd"]

    action = request.form["action"].strip().lower()

    try:
        resp = requests.post(API_URL + "/match", data=json.dumps({"name": uname, "passwd": passwd, "action": action, "match": request.form["who"]}), headers={'content-type': 'application/json'})
        resp = json.loads(resp.text)
    except Exception as e:
        return redirect("/error?msg=%s" % "Failed to (un)match", code=303)

    if resp["status"] != "OK":
        return redirect("/error?msg=%s" % resp["msg"], code=303)

    return redirect('/user_info%s' % ("?who=" + request.form["who"]) if "who" in request.form else "", code=303)

@app.route("/browse", methods=["GET", "POST"])
def browse():
    if "uname" not in session:
        return redirect("/error?msg=%s" % "Please log in first", code=303)

    uname = session["uname"]
    passwd = session["passwd"]

    start = int(request.args["s"]) if "s" in request.args else 0
    end = int(request.args["e"]) if "e" in request.args else 25
    next_start = end
    next_end = end + 25
    prev_start = max(0, start - 25)
    prev_end = max(start, 25)
    limit_loc = request.args["l"] if "l" in request.args else "true"

    try:
        resp = requests.post(API_URL + "/get", data=json.dumps({"name": uname, "passwd": passwd, "what": "users", "which": limit_loc, "start": start, "stop": end}), headers={'content-type': 'application/json'})
        resp = json.loads(resp.text)
    except Exception as e:
        return redirect("/error?msg=%s" % "Failed to find users", code=303)

    if resp["status"] != "OK":
        return redirect("/error?msg=%s" % resp["msg"], code=303)

    data = {}
    data["next_start"] = next_start
    data["next_end"] = next_end
    data["prev_start"] = prev_start
    data["prev_end"] = prev_end
    data["start"] = start
    data["end"] = end
    data["limit_loc"] = limit_loc
    data["here"] = "browse"

    for i, r in enumerate(resp["ret"]):
        resp["ret"][i]["sex"] = "M" if r["male"] else "F"
        resp["ret"][i]["prefer"] = PREF_NAMES[r["pref"]]
        if "descr" in resp["ret"][i]:
            resp["ret"][i]["descr"] = Markup(markdown.markdown(resp["ret"][i]["descr"]))

    data["people"] = resp["ret"]

    template = env.get_template("html/browse.html")
    return template.render(data)

@app.route("/report", methods=["GET", "POST"])
def report():
    if "uname" not in session:
        return redirect("/error?msg=%s" % "Please log in first", code=303)
 
    uname = session["uname"]
    passwd = session["passwd"]

    try:
        resp = requests.post(API_URL + "/report", data=json.dumps({"reason": request.form["reason"] if "reason" in request.form else "", "target": request.form["target"], "name": uname, "passwd": passwd, "what": "users"}), headers={'content-type': 'application/json'})
        resp = json.loads(resp.text)
    except Exception as e:
        return redirect("/error?msg=%s" % "Failed to report, internal error", code=303)

    if resp["status"] != "OK":
        return redirect("/error?msg=%s" % resp["msg"], code=303)

    return redirect("/browse", code=303)

def do_login(name, passwd):
    try:
        if len(name) == 0:
            raise Exception
        resp = requests.post(API_URL + "/login", data=json.dumps({"name": name, "passwd": passwd}), headers={'content-type': 'application/json'})
        return json.loads(resp.text)
    except Exception as e:
        return {"status": "error", "msg": "Failed to login. Did you input a username and password?"}

def do_register(name, passwd):
    try:
        if len(name) == 0:
            raise Exception
        resp = requests.post(API_URL + "/register", data=json.dumps({"name": name, "passwd": passwd}), headers={'Content-Type': 'application/json'})
        return json.loads(resp.text)
    except Exception as e:
        if len(name) == 0 or len(passwd) == 0:
                return {"status": "error", "msg": "Enter a name and password to register"}
        return {"status": "error", "msg": "Internal Error"}

def get_user_info(name, passwd, who):
    resp = requests.post(API_URL + "/get", data=json.dumps({"name": name, "passwd": passwd, "what": "user", "which": who}), headers={'content-type': 'application/json'})
    try:
        info = json.loads(resp.text)
        if info["status"] == "OK":
            for k, v in info["ret"].items():
                if v is None:
                    info["ret"][k] = ""

        if "descr" in info["ret"]:
            info["ret"]["mddescr"] = Markup(markdown.markdown(info["ret"]["descr"]))
        return info
    except Exception as e:
        print("Failed to get info:", resp.text, file=errlog)
        return {"status": "error", "msg": "Internal Error"}

@app.route("/enter", methods=["GET", "POST"])
def enter():
    uname = request.form["uname"].strip().lower().replace("|", "_")
    action = request.form["action"].strip().lower()
    passwd = hashlib.sha256(request.form["passwd"].encode('utf-8')).hexdigest()
    if action == "login":
        resp = do_login(uname, passwd)
        if resp["status"] != "OK":
            return redirect("/error?msg=%s" % resp["msg"], code=303)
        else:
            session["uname"] = uname
            session["passwd"] = passwd
            return redirect("/browse", code=303)
    elif action == "register":
        resp = do_register(uname, passwd)
        if resp["status"] != "OK":
            return redirect("/error?msg=%s" % resp["msg"], code=303)
        else:
            resp = do_login(uname, passwd)
            if resp["status"] != "OK":
                return redirect("/error?msg=%s" % resp["msg"], code=303)
            else:
                session["uname"] = request.form["uname"]
                session["passwd"] = passwd
                return redirect("/user_info", code=303)
    else:
        print("ERROR: unknown action", action, file=errlog)
        return redirect("/error?msg=%s" % "Internal Error", code=303)

@app.route("/forum", methods=["GET", "POST"])
def forum():
    if "uname" not in session:
        return redirect("/error?msg=%s" % "Please log in first", code=303)
 
    uname = session["uname"]
    passwd = session["passwd"]

    data = {}
    data["uname"] = uname
    data["thread"] = int(request.args["t"] if "t" in request.args else "-1")

    try:
        resp = requests.post(API_URL + "/get", data=json.dumps({"name": uname, "passwd": passwd, "what": "posts", "which": data["thread"]}), headers={'content-type': 'application/json'})
        resp = json.loads(resp.text)
    except Exception as e:
        return redirect("/error?msg=%s" % "Failed to get forum contents", code=303)

    if resp["status"] != "OK":
        return redirect("/error?msg=%s" % resp["msg"], code=303)
    
    template = env.get_template("html/forum.html")
    return template.render(posts=resp["ret"], thread=data["thread"])

@app.route("/post", methods=["POST"])
def post():
    if "uname" not in session:
        return redirect("/error?msg=%s" % "Please log in first", code=303)
 
    uname = session["uname"]
    passwd = session["passwd"]
    thread = int(request.form["t"] if "t" in request.form else "-1")
    
    if thread < 0:
        if "title" not in request.form or request.form["title"] == "":
            return redirect("/error?msg=%s" % "Can't create threads without a title", code=303)

    try:
        resp = requests.post(API_URL + "/post", data=json.dumps({"thread": thread, "name": uname, "passwd": passwd, "content": Markup(markdown.markdown(html.escape(request.form["content"] if "content" in request.form else ""))), "title": html.escape(request.form["title"]) if "title" in request.form else ""}), headers={'content-type': 'application/json'})
        resp = json.loads(resp.text)
    except Exception as e:
        return redirect("/error?msg=%s" % "Failed to report, internal error", code=303)

    if resp["status"] != "OK":
        return redirect("/error?msg=%s" % resp["msg"], code=303)

    return redirect("/forum?t=%s" % (resp["ret"] if thread < 0 else thread), code=303)

if __name__ == "__main__":
    app.run()
