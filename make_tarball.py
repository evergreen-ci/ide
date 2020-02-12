#!/usr/bin/env python3

import requests
import json
import os
import tarfile
import argparse
import tempfile
import shutil
import io
import boto3
from datetime import datetime

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


def make_tarball(input_dir):
    print("creating tarball")
    fo = io.BytesIO()
    with tarfile.open(fileobj=fo, mode="w:gz") as tar:
        for file in os.listdir(input_dir):
            tar.add(os.path.join(input_dir, file), arcname=file)
        tar.add("settings.json")

    fo.seek(0)
    return fo.read()

def get_extension_list(extension_json_path):
    with open(extension_json_path) as f:
        return json.load(f)

def upload_to_s3(bucket, tarball, object_name):
    print("uploading to s3")
    s3_client = boto3.client("s3")
    s3_client.upload_fileobj(tarball, bucket, object_name)


def main():
    parser = argparse.ArgumentParser(description="Create a code-server distribution for Evergreen virtual-workstations")
    parser.add_argument("extensions", help="JSON file listing extensions to include")
    parser.add_argument("--release", help="code-server release", default="latest")
    parser.add_argument("--architecture", help="code-server binary for ARCHITECTURE", default="linux-x86_64", choices=["linux-x86_64", "linux-arm64", "darwin-x86_64", "alpine-x86_64", "alpine-arm64"])
    parser.add_argument("--destination", help="Local directory to output the tarball")
    parser.add_argument("--s3_bucket", help="s3 bucket to upload to")
    args = parser.parse_args()

    extensions = get_extension_list(args.extensions)
    with tempfile.TemporaryDirectory() as tempDir:
        download_extensions(extensions, tempDir)
        download_code_server(args.release, args.architecture, tempDir)
        tarball = make_tarball(tempDir)

    output_name = "code-server_{}.tgz".format(datetime.now().isoformat(timespec="minutes"))
    if args.destination is not None:
        with open(os.path.join(args.destination, output_name), "wb") as dest:
            dest.write(tarball)
    if args.s3_bucket is not None:
        upload_to_s3(args.s3_bucket, tarball, output_name)
        

if __name__ == "__main__":
    main()