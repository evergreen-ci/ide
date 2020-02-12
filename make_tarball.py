#!/usr/bin/env python3

import requests
import json
import os
import tarfile
import argparse
import tempfile
import shutil

# https://stackoverflow.com/questions/37071388/how-can-i-install-visual-studio-code-extensions-offline
EXTENSION_DOWNLOAD_URL = "https://{publisher}.gallery.vsassets.io/_apis/public/gallery/publisher/{publisher}/extension/{extension_name}/{extension_version}/assetbyname/Microsoft.VisualStudio.Services.VSIXPackage"
CODE_SERVER_RELEASES_URL = "https://api.github.com/repos/cdr/code-server/releases/{release}"
CODE_SERVER_RELEASE_ASSET_URL = "https://api.github.com/repos/cdr/code-server/releases/assets/{asset_id}"

def download_extensions(extensions, destination_dir):
    for extension in extensions:
        print("getting extension {}.{}".format(extension["publisher"], extension["name"]))
        url = EXTENSION_DOWNLOAD_URL.format(extension_name=extension["name"], publisher=extension["publisher"], extension_version=extension["version"])
        r = requests.get(url)

        if r.status_code != 200:
            raise RuntimeError("can't get extension {}".format(extension["name"]))

        with open(os.path.join(destination_dir, extension["publisher"]+"."+extension["name"]+".vsix"), "wb") as f:
            f.write(r.content)
            

def download_code_server(release, architecture, destination_dir):
    print("getting code server")

    r = requests.get(CODE_SERVER_RELEASES_URL.format(release=release))
    if r.status_code != 200:
        raise RuntimeError("can't get release info from GitHub")
    
    release_info = r.json()
    asset_id = ""
    asset_name = ""
    for asset in release_info["assets"]:
        if architecture in asset["name"]:
            asset_id = asset["id"]
            asset_name = asset["name"]
    
    if asset_id == "":
        raise ValueError("architecture {} not found in release {}".format(architecture, release))

    r = requests.get(CODE_SERVER_RELEASE_ASSET_URL.format(asset_id=asset_id), headers={"Accept": "application/octet-stream"}, stream=True)
    if r.status_code != 200:
        raise RuntimeError("can't get asset id {} from GitHub".format(asset_id))
    
    with tempfile.TemporaryDirectory() as temp_dir:
        with tarfile.open(fileobj=r.raw) as tf:
            tf.extractall(temp_dir)
        shutil.copy(os.path.join(temp_dir, asset_name[:-7], "code-server"), destination_dir)


def make_tarball(input_dir, output_filename):
    print("writing tarball")
    with tarfile.open(output_filename, "w:gz") as tar:
        for file in os.listdir(input_dir):
            tar.add(os.path.join(input_dir, file), arcname=file)
        tar.add("settings.json")

def get_extension_list(extension_json_path):
    with open(extension_json_path) as f:
        return json.load(f)

def upload_to_s3(key, secret, location):
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("extensions", help="JSON file listing extensions to include")
    parser.add_argument("--destination", help="Path to output the tarball")
    parser.add_argument("--release", help="code-server release", default="latest")
    parser.add_argument("--architecture", help="code-server binary for ARCHITECTURE", default="linux-x86_64")
    args = parser.parse_args()

    extensions = get_extension_list(args.extensions)
    with tempfile.TemporaryDirectory() as tempDir:
        download_extensions(extensions, tempDir)
        download_code_server(args.release, args.architecture, tempDir)
        make_tarball(tempDir, os.path.join(args.destination or os.getcwd(), "code-server.tgz"))

if __name__ == "__main__":
    main()