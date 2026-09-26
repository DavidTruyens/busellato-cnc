"""Runs INSIDE Fusion (via the Fusion MCP: exec(open(PATH).read())).

capture_cnc(): mode A - posts every NC program once with post/tests/cnc-capture.cps, which
               copies the intermediate .cnc to post/tests/cases/<NAME>.cnc plus a
               <NAME>.json sidecar (programName, unit - not stored in the .cnc).
post_all(variants): mode B - posts every NC program with post/busellato-cnc90.cps
               and writes post/tests/out/<NAME>[.<variant>].nc and .status.
"""
import json
import os
import shutil
import struct
import tempfile

import adsk.cam
import adsk.core

REPO = '/Users/davidtruyens/Source/busellato-cnc'
POSTS_DIR = os.path.expanduser('~/Library/Application Support/Autodesk/Fusion 360 CAM/Posts')
CASES = os.path.join(REPO, 'post', 'tests', 'cases')
OUT = os.path.join(REPO, 'post', 'tests', 'out')


def _cam():
    app = adsk.core.Application.get()
    return adsk.cam.CAM.cast(app.activeDocument.products.itemByProductType('CAMProductType'))


def _post_config(file_name):
    lib = adsk.cam.CAMManager.get().libraryManager.postLibrary
    root = lib.urlByLocation(adsk.cam.LibraryLocations.LocalLibraryLocation)
    for url in lib.childAssetURLs(root):
        if url.toString().endswith(file_name):
            return lib.postConfigurationAtURL(url)
    raise RuntimeError(f'{file_name} not found in the local post library ({POSTS_DIR})')


def _post(ncp, post_file, out_dir, props=None):
    ncp.postConfiguration = _post_config(post_file)
    ncp.parameters.itemByName('nc_program_output_folder').value.value = out_dir
    ncp.parameters.itemByName('nc_program_openInEditor').value.value = False
    if props:
        params = ncp.postParameters
        for key, value in props.items():
            p = params.itemByName(key)
            if p is None:
                raise RuntimeError(f'post property {key} not found')
            p.value.value = value
        ncp.updatePostParameters(params)
    return ncp.postProcess(adsk.cam.NCProgramPostProcessOptions.create())


# Metadata parameters Fusion writes into every intermediate .cnc that identify the user,
# the machine or the cloud document. Layout: <uint32 len><key ASCII><uint32 char count><UTF-16LE value>.
REDACT_PARAMS = ['hostname', 'username', 'user-id', 'user-email', 'display-name', 'document-path',
                 'document-id', 'model-version', 'datafile-id', 'datafile-version-id', 'datafile-webURL']
_PARAM_PREFIX = b'http://www.cimco-software.com/namespace/nc/parameter/'


def redact(path):
    """Overwrite the REDACT_PARAMS values in a captured .cnc with same-length 'x' filler
    (binary layout unchanged), plus any other occurrence (UTF-16 or ASCII) of those values that
    are at least 8 characters long."""
    data = bytearray(open(path, 'rb').read())
    values = set()
    for name in REDACT_PARAMS:
        key = _PARAM_PREFIX + name.encode('ascii')
        key = struct.pack('<I', len(key)) + key  # keys are length-prefixed: exact match only
        start = 0
        while True:
            i = data.find(key, start)
            if i < 0:
                break
            j = i + len(key)
            start = j
            (n,) = struct.unpack('<I', data[j:j + 4])
            raw = bytes(data[j + 4:j + 4 + 2 * n])
            if len(raw) != 2 * n:
                raise ValueError(f'{path}: truncated value for {name}')
            text = raw.decode('utf-16-le')
            if not text.isprintable():
                raise ValueError(f'{path}: {name} is not a UTF-16 text value')
            if text:
                values.add(text)
            data[j + 4:j + 4 + 2 * n] = 'x'.encode('utf-16-le') * n
    for text in (v for v in values if len(v) >= 8):  # short ones ('Mac', 'root') would hit other data
        for enc in ('utf-16-le', 'ascii'):
            try:
                needle = text.encode(enc)
            except UnicodeEncodeError:
                continue
            filler = 'x'.encode(enc) * len(text)
            data = bytearray(bytes(data).replace(needle, filler))
    with open(path, 'wb') as fh:
        fh.write(data)
    return sorted(values)


def capture_cnc(stand_in_post='cnc-capture.cps'):
    """Fusion deletes its intermediate .cnc right after posting, so searching for it
    afterwards finds nothing. The stand-in post post/tests/cnc-capture.cps copies it
    (getIntermediatePath()) into the output folder while posting, and writes a JSON
    sidecar with what Fusion passes that is not in the .cnc (programName, unit)."""
    shutil.copyfile(os.path.join(REPO, 'post', 'tests', stand_in_post), os.path.join(POSTS_DIR, stand_in_post))
    os.makedirs(CASES, exist_ok=True)
    found = {}
    cam = _cam()
    for i in range(cam.ncPrograms.count):
        ncp = cam.ncPrograms.item(i)
        with tempfile.TemporaryDirectory() as tmp:
            ok = _post(ncp, stand_in_post, tmp)
            cnc = os.path.join(tmp, 'intermediate.cnc')
            sidecar = [f for f in os.listdir(tmp) if f.endswith('.json')]
            if ok and os.path.exists(cnc) and sidecar:
                shutil.copyfile(cnc, os.path.join(CASES, ncp.name + '.cnc'))
                redact(os.path.join(CASES, ncp.name + '.cnc'))
                shutil.copyfile(os.path.join(tmp, sidecar[0]), os.path.join(CASES, ncp.name + '.json'))
                found[ncp.name] = os.path.getsize(cnc)
    return found


def post_all(variants):
    """variants: {suffix: {case: props}}; suffix '' = default properties."""
    shutil.copyfile(os.path.join(REPO, 'post', 'busellato-cnc90.cps'),
                    os.path.join(POSTS_DIR, 'busellato-cnc90.cps'))
    os.makedirs(OUT, exist_ok=True)
    cam = _cam()
    programs = {cam.ncPrograms.item(i).name: cam.ncPrograms.item(i) for i in range(cam.ncPrograms.count)}
    report = {}
    for suffix, cases in variants.items():
        for case, props in cases.items():
            key = case + (('.' + suffix) if suffix else '')
            with tempfile.TemporaryDirectory() as tmp:
                ok = _post(programs[case], 'busellato-cnc90.cps', tmp, props)
                produced = [f for f in os.listdir(tmp) if not f.endswith('.log')]
                text = open(os.path.join(tmp, produced[0]), 'rb').read() if (ok and produced) else b''
            with open(os.path.join(OUT, key + '.nc'), 'wb') as fh:
                fh.write(text)
            with open(os.path.join(OUT, key + '.status'), 'w') as fh:
                fh.write('ok' if ok else 'failed')
            report[key] = ok
    return report
