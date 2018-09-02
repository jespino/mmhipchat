import click
import tarfile
import sys
import json
import os
import shutil
from datetime import datetime
import dateutil.parser


class MMExport():
    def __init__(self, output):
        os.makedirs(output, exist_ok=True)
        self.output_dir = output
        self.output_json = open(os.path.join(
            output, "hipchat-export.json"), "w")
        self.output_json.write(json.dumps({
            "type": "version",
            "version": 1
        }) + "\n")

    def addTeam(self, team):
        line = json.dumps({"type": "team", "team": team})
        self.output_json.write(line + "\n")

    def addChannel(self, channel):
        line = json.dumps({"type": "channel", "channel": channel})
        self.output_json.write(line + "\n")

    def addUser(self, user):
        line = json.dumps({"type": "user", "user": user})
        self.output_json.write(line + "\n")

    def addEmoji(self, user):
        line = json.dumps({"type": "emoji", "emoji": user})
        self.output_json.write(line + "\n")

    def addPost(self, post):
        line = json.dumps({"type": "post", "post": post})
        self.output_json.write(line + "\n")

    def addDirectChannel(self, direct_channel):
        line = json.dumps(
            {"type": "direct_channel", "direct_channel": direct_channel})
        self.output_json.write(line + "\n")

    def addDirectPost(self, direct_post):
        line = json.dumps({"type": "direct_post", "direct_post": direct_post})
        self.output_json.write(line + "\n")

    def close():
        self.output_json.close()

    def copyEmojiImage(self, tarFile, path):
        emoji_id = path.split("/")[0]
        filename = path.split("/")[1]
        os.makedirs(os.path.join(self.output_dir, "export-files",
                                 "emojis", emoji_id), exist_ok=True)
        with tarFile.extractfile(os.path.join("files", "img", "emoticons", emoji_id, filename)) as fsrc:
            with open(os.path.join(self.output_dir, "export-files", "emojis", emoji_id, filename), "wb") as fdst:
                fdst.write(fsrc.read())
        return os.path.join("export-files", "emojis", emoji_id, filename)

    def copyPostAttachment(self, tarFile, path):
        directory = path.split("/")[0]
        filename = path.split("/")[1]
        os.makedirs(os.path.join(self.output_dir, "export-files",
                                 "attachments", directory), exist_ok=True)
        with tarFile.extractfile(os.path.join("users", "files", directory, filename)) as fsrc:
            with open(os.path.join(self.output_dir, "export-files", "attachments", directory, filename), "wb") as fdst:
                fdst.write(fsrc.read())
        return os.path.join("export-files", "attachments", directory, filename)

    def copyUserAvatar(self, tarFile, path):
        user_id = path.split("/")[2]
        filename = path.split("/")[3]
        os.makedirs(os.path.join(self.output_dir, "export-files",
                                 "users", user_id), exist_ok=True)
        with tarFile.extractfile(os.path.join("users", user_id, "avatars", filename)) as fsrc:
            with open(os.path.join(self.output_dir, "export-files", "users", user_id, filename), "wb") as fdst:
                fdst.write(fsrc.read())
        return os.path.join("export-files", "users", user_id, filename)


@click.command()
@click.argument("hipchat-export")
@click.argument("output-directory")
def convert(hipchat_export, output_directory):
    try:
        exportFile = tarfile.open(hipchat_export)
    except Exception as e:
        print(e)
        sys.exit(1)

    mmexport = MMExport(output_directory)

    team = {
        "name": "hipchat",
        "display_name": "Hipchat",
        "type": "I",
        "description": "",
        "allow_open_invite": False,
    }

    mmexport.addTeam(team)

    with exportFile.extractfile("emoticons.json") as fd:
        emojis = json.load(fd)

    for emoji in emojis['Emoticons']:
        mmexport.addEmoji({
            "name": emoji['shortcut'],
            "image": mmexport.copyEmojiImage(exportFile, emoji['path']),
        })

    with exportFile.extractfile("rooms.json") as fd:
        rooms = json.load(fd)

    roomMembers = {}
    roomAdmins = {}
    room_names = {}

    for room in map(lambda r: r['Room'], rooms):
        if 'is_deleted' in room and room['is_deleted']:
            print("Deleted room {} not imported".format(room['name']))
            continue

        if 'is_archived' in room and room['is_archived']:
            print("Archied room {} imported as non archived because we don't support it at import time yet".format(
                room['name']))

        mmexport.addChannel({
            "team": team["name"],
            "name": room["canonical_name"],
            "display_name": room["name"],
            "type": "O" if room['privacy'] == 'public' else "P",
            "header": room["topic"],
            "purpose": "",
        })
        room_names[room['id']] = room["canonical_name"]
        for member in room['members']:
            if member in roomMembers:
                roomMembers[member].append(room['canonical_name'])
            else:
                roomMembers[member] = [room['canonical_name']]

        for admin in room['room_admins']:
            if admin in roomAdmins:
                roomAdmins[admin].append(room['canonical_name'])
            else:
                roomAdmins[admin] = [room['canonical_name']]

    with exportFile.extractfile("users.json") as fd:
        users = json.load(fd)

    user_names = {}
    for user in map(lambda u: u['User'], users):
        if user['account_type'] == "guest":
            print("Not migrating user account {} because guest accounts aren't supported in mattermost".format(
                user['name']))
            continue

        if 'is_deleted' in user and user['is_deleted']:
            print("Not migrating user account {} because is deleted".format(
                user['name']))
            continue

        channels = []
        if user['id'] in roomMembers:
            for channel in roomMembers[user['id']]:
                channels.append({
                    "name": channel,
                    "roles": "channel_user",
                })

        if user['id'] in roomAdmins:
            for channel in roomAdmins[user['id']]:
                channels.append({
                    "name": channel,
                    "roles": "channel_admin channel_user",
                })

        mmexport.addUser({
            "profile_image": mmexport.copyUserAvatar(exportFile, user['avatar']) if 'avatar' in user and user['avatar'] != "" else "",
            "username": user['mention_name'].lower(),
            "email": user['email'],
            "nickname": user['name'],
            "position": user['title'],
            "roles": "system_admin system_user" if user['account_type'] == "admin" else "system_user",
            "teams": [{
                "name": team['name'],
                "roles": "team_user",
                "channels": channels
            }],
        })

        user_names[user['id']] = user['mention_name']

    for room_id in room_names.keys():
        with exportFile.extractfile("rooms/{}/history.json".format(room_id)) as fd:
            posts = json.load(fd)

        for post in posts:
            if "UserMessage" in post:
                msg = post['UserMessage']
                if "deleted" in msg and msg["deleted"]:
                    print("Not migrating deleted message {}".format(msg['id']))

                mmexport.addPost({
                    "team": team['name'],
                    "channel": room_names[room_id],
                    "user": user_names[msg['sender']['id']],
                    "message": msg['message'],
                    # TODO: Properly move miliseconds to the correct position
                    "create_at": int(dateutil.parser.isoparse(msg['timestamp'].split(" ")[0]).timestamp()),
                    "attachments": [{"path": mmexport.copyPostAttachment(exportFile, msg["attachment"]["path"])}] if 'attachment' in msg and msg["attachment"] else [],
                })

    direct_channels = {}
    for user_id in user_names.keys():
        with exportFile.extractfile("users/{}/history.json".format(user_id)) as fd:
            posts = json.load(fd)

        for post in posts:
            post = post['PrivateUserMessage']
            key = "-".join(map(str,
                               sorted([post["sender"]["id"], post["receiver"]["id"]])))
            direct_channels[key] = sorted(
                [post["sender"]["id"], post["receiver"]["id"]])

    for dc in direct_channels.values():
        mmexport.addDirectChannel({
            "members": [user_names[dc[0]], user_names[dc[1]]]
        })

    for user_id in user_names.keys():
        with exportFile.extractfile("users/{}/history.json".format(user_id)) as fd:
            posts = json.load(fd)

        for post in posts:
            if "PrivateUserMessage" in post:
                msg = post['PrivateUserMessage']
                if "deleted" in msg and msg["deleted"]:
                    print("Not migrating deleted message {}".format(msg['id']))

                mmexport.addDirectPost({
                    "channel_members": [
                        user_names[msg["sender"]["id"]],
                        user_names[msg["receiver"]["id"]],
                    ],
                    "user": user_names[msg['sender']['id']],
                    "message": msg['message'],
                    # TODO: Properly move miliseconds to the correct position
                    "create_at": int(dateutil.parser.isoparse(msg['timestamp'].split(" ")[0]).timestamp()),
                    "attachments": [{"path": mmexport.copyPostAttachment(exportFile, msg["attachment"]["path"])}] if 'attachment' in msg and msg["attachment"] else [],
                })


if __name__ == "__main__":
    convert()
