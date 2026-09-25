/**
  Stand-in post used by post/tests/fusion_capture.py:capture_cnc() (runs inside Fusion).

  Fusion deletes its intermediate .cnc file as soon as posting ends, so this post copies
  it (getIntermediatePath()) next to its own output. Its own output is a small JSON file
  with the values Fusion passes to a post that are NOT stored in the .cnc (program name,
  comment, unit); tests/test_post.py hands them back to the CLI post engine as properties.
*/
description = "Busellato test harness: capture intermediate .cnc";
vendor = "busellato-cnc";
extension = "json";
setCodePage("ascii");
capabilities = CAPABILITY_MILLING | CAPABILITY_JET;

function onOpen() {
  var src = getIntermediatePath();
  var dst = FileSystem.getCombinedPath(FileSystem.getFolderPath(getOutputPath()), "intermediate.cnc");
  FileSystem.copyFile(src, dst);
  writeln(JSON.stringify({
    programName: String(programName),
    programComment: String(programComment),
    unit: unit
  }));
}

function onSection() {
}

function onClose() {
}
