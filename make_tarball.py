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
from datetime import date
from pathlib import Path

# https://stackoverflow.com/questions/37071388/how-can-i-install-visual-studio-code-extensions-offline
EXTENSION_DOWNLOAD_URL = "https://{publisher}.gallery.vsassets.io/_apis/public/gallery/publisher/{publisher}/extension/{extension_name}/{extension_version}/assetbyname/Microsoft.VisualStudio.Services.VSIXPackage"
CODE_SERVER_RELEASES_URL = "https://api.github.com/repos/cdr/code-server/releases/{release}"
CODE_SERVER_RELEASE_ASSET_URL = "https://api.github.com/repos/cdr/code-server/releases/assets/{asset_id}"
ICON_PATH = "src/browser/media/"
PRODUCT_PATH = "lib/vscode/product.json"
PWA_MANIFEST_PATH = "src/browser/media/manifest.json"
PRODUCT_NAME = "Evergreen - IDE"
PRODUCT_NAME_SHORT = "IDE"

def download_extensions(extensions, destination_dir):
    Path(destination_dir).mkdir(parents=True, exist_ok=True)
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
        shutil.copytree(os.path.join(temp_dir, asset_name[:-7]), destination_dir)

def customize_code_server(base_dir):
    print("replacing icons")
    for icon_file in os.listdir("icons"):
        shutil.copy(os.path.join("icons", icon_file), os.path.join(base_dir, ICON_PATH))
    print("changing application name in product.json")
    with open(os.path.join(base_dir, PRODUCT_PATH)) as product_config:
        product_json = json.load(product_config)
    product_json["nameShort"] = PRODUCT_NAME_SHORT
    product_json["nameLong"] = PRODUCT_NAME
    with open(os.path.join(base_dir, PRODUCT_PATH), 'w') as product_config:
        json.dump(product_json, product_config)

    print("changing application name in PWA's manifest.json")
    with open(os.path.join(base_dir, PWA_MANIFEST_PATH)) as pwa_manifest:
        manifest_json = json.load(pwa_manifest)
    manifest_json["short_name"] = PRODUCT_NAME_SHORT
    manifest_json["name"] = PRODUCT_NAME
    with open(os.path.join(base_dir, PWA_MANIFEST_PATH), 'w') as pwa_manifest:
        json.dump(manifest_json, pwa_manifest)

def make_tarball(code_server_dir, extensions_dir, output_path):
    print("creating tarball")
    with tarfile.open(output_path, mode="w:gz") as tar:
        tar.add(code_server_dir, arcname="code-server")
        tar.add(extensions_dir, arcname="code-server/extension_packages")
        tar.add("User", arcname="code-server/User")
        tar.add("service", arcname="code-server/service")

def get_extension_list(extension_json_path):
    with open(extension_json_path) as f:
        return json.load(f)

def upload_to_s3(bucket, tarball_path, object_name):
    print("uploading to s3")
    s3_client = boto3.client("s3")
    s3_client.upload_file(tarball_path, bucket, object_name, ExtraArgs={"ACL": "public-read"})


def main():
    parser = argparse.ArgumentParser(description="Create a code-server distribution for Evergreen virtual-workstations")
    parser.add_argument("extensions", help="JSON file listing extensions to include")
    parser.add_argument("--release", help="code-server release", default="latest")
    parser.add_argument("--architecture", help="code-server binary for ARCHITECTURE", default="linux-amd64", choices=["linux-amd64", "linux-arm64", "macos-amd64"])
    parser.add_argument("--destination", help="Local directory to output the tarball", default=os.getcwd())
    parser.add_argument("--s3_bucket", help="s3 bucket to upload to")
    args = parser.parse_args()

    extensions = get_extension_list(args.extensions)
    with tempfile.TemporaryDirectory() as tempDir:
        code_server_dir = os.path.join(tempDir, "code-server")
        extensions_dir = os.path.join(tempDir, "extension_packages")
        download_code_server(args.release, args.architecture, code_server_dir)
        customize_code_server(code_server_dir)
        download_extensions(extensions, extensions_dir)
        output_name = "{date}_{architecture}_code-server.tgz".format(architecture=args.architecture, date=date.today().isoformat())
        make_tarball(code_server_dir, extensions_dir, os.path.join(args.destination, output_name))

    if args.s3_bucket is not None:
        upload_to_s3(args.s3_bucket, os.path.join(args.destination, output_name), "evergreen/vscode/{}".format(output_name))
        

if __name__ == "__main__":
    main()