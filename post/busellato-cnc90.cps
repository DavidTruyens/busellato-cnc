/**
  Busellato S.EASY - TPA CNC90 v3.0 post processor.
  Writes a CNC90 program source for C:\CNC90\MOD1\SORG\SRG\<first letter>\<NAME>.
  Spec: docs/superpowers/specs/2026-09-25-fusion-post-design.md (busellato-cnc repo).
*/

description = "Busellato S.EASY - TPA CNC90";
vendor = "TPA";
longDescription = "CNC90 ISO-DGT program source: 2D contour, 2D pocket, vertical drilling, top face (P5).";
certificationLevel = 2;
minimumRevision = 45917;
extension = "";
setCodePage("ascii");
capabilities = CAPABILITY_MILLING;
tolerance = spatial(0.002, MM);
minimumChordLength = spatial(0.25, MM);
minimumCircularRadius = spatial(0.01, MM);
maximumCircularRadius = spatial(100000, MM);
minimumCircularSweep = toRad(0.01);
maximumCircularSweep = toRad(180);
allowHelicalMoves = true;
allowedCircularPlanes = undefined;

properties = {
  feedUnit: {title: "Feed unit", description: "m/min: Fusion mm/min / 1000 (F1 = 1 m/min). mm/min: unchanged.",
    type: "enum", values: [{id: "mpm", title: "m/min"}, {id: "mmpm", title: "mm/min"}], value: "mpm", scope: "post"},
  origin: {title: "Origin", description: "Reference origin of the machine.",
    type: "enum", values: [{id: "G54", title: "G54"}, {id: "G55", title: "G55"}], value: "G54", scope: "post"},
  mirrorY: {title: "Mirror Y", description: "Mirror Y about the stock centre and swap G2/G3.",
    type: "boolean", value: false, scope: "post"},
  arcOutput: {title: "Arc output", description: "arcs: G2/G3. lines: straight segments only (emergency fallback).",
    type: "enum", values: [{id: "arcs", title: "G2/G3 arcs"}, {id: "lines", title: "Straight lines only"}], value: "arcs", scope: "post"},
  segmentLength: {title: "Segment length (mm)", description: "Segment length when arc output = lines, or for an allowed Z-changing arc.",
    type: "number", value: 2, scope: "post"},
  mergeTolerance: {title: "Merge tolerance (mm)", description: "Collinear straight moves within this distance are merged.",
    type: "number", value: 0.05, scope: "post"},
  lineWarning: {title: "Warn above N lines", description: "Largest program the machine is known to run is ~250 lines.",
    type: "integer", value: 250, scope: "post"},
  maxDepthBelow: {title: "Max depth below stock (mm)", description: "Deeper cuts than stock thickness + this are refused.",
    type: "number", value: 5, scope: "post"},
  allowedTools: {title: "Allowed tool numbers", description: "Comma separated numbers and ranges, e.g. 1-30,65,66.",
    type: "string", value: "1-30,65,66", scope: "post"}
};

var TOP = 0.0005;          // mm; at or above this Z counts as "not in the material"
var moves = [];            // output lines between G150 and M2, as objects
var stock = null;          // {lx, ly, lz, ux, uy, uz} in WCS mm
var inContour = false;
var progName = "";
var progComment = "";
var sectionTool = 0;
var sectionRpm = 0;

function fmt(v) {
  var r = Math.round(v * 1000) / 1000;
  if (Math.abs(r) < 0.0005) {
    r = 0;
  }
  return String(r);
}

function pad2(n) {
  return (n < 10 ? "0" : "") + n;
}

function outY(y) {
  return getProperty("mirrorY") ? (stock.ly + stock.uy - y) : y;
}

function feedOut(f) {
  return getProperty("feedUnit") == "mpm" ? f / 1000 : f;
}

function onOpen() {
  setEOL("\r\n");
  if (unit != MM) {
    error("Set the NC program output units to millimetres.");
  }
  progName = String(programName || "").toUpperCase();
  if (!/^[A-Z0-9_-]{1,8}$/.test(progName)) {
    error("Invalid program name '" + programName + "': use 1-8 characters A-Z, 0-9, _ or - (DOS file name).");
  }
  progComment = String(programComment || "").toUpperCase().replace(/[^\x20-\x7E]/g, "").replace(/[()]/g, "").substr(0, 30);
}

function parseAllowed(text) {
  var allowed = {};
  var parts = String(text).split(",");
  for (var i = 0; i < parts.length; ++i) {
    var p = parts[i].replace(/\s+/g, "");
    if (!p) {
      continue;
    }
    var m = p.match(/^(\d+)-(\d+)$/);
    if (m) {
      for (var t = parseInt(m[1], 10); t <= parseInt(m[2], 10); ++t) {
        allowed[t] = true;
      }
    } else if (/^\d+$/.test(p)) {
      allowed[parseInt(p, 10)] = true;
    } else {
      error("Allowed tool numbers: cannot read '" + parts[i] + "'.");
    }
  }
  return allowed;
}

function onRadiusCompensation() {
  if (radiusCompensation != RADIUS_COMPENSATION_OFF) {
    error("Cutter compensation must be 'In computer' (found compensation in control).");
  }
}

function onSection() {
  inContour = false;
  if (!stock) {
    var box = getWorkpiece();
    if (!box || !(box.upper.x > box.lower.x)) {
      error("No stock defined in the setup.");
    }
    if (Math.abs(box.upper.z) > 0.01) {
      error("The setup origin must be on the TOP surface of the stock (stock top is at Z=" + fmt(box.upper.z) + ").");
    }
    stock = {lx: box.lower.x, ly: box.lower.y, lz: box.lower.z, ux: box.upper.x, uy: box.upper.y, uz: box.upper.z};
  }
  sectionTool = tool.number;
  sectionRpm = tool.spindleRPM;
  var strategy = currentSection.strategy || getParameter("operation-strategy", "");
  if (["contour2d", "pocket2d", "drill"].indexOf(strategy) < 0) {
    error("Operation " + getParameter("operation-comment", "") + " (" + strategy +
      ") is not supported. Use 2D contour, 2D pocket or drilling.");
  }
  if (hasParameter("operation:compensationType") && getParameter("operation:compensationType") != "computer") {
    error("Cutter compensation must be 'In computer' in operation " + getParameter("operation-comment", "") + ".");
  }
  if (!parseAllowed(getProperty("allowedTools"))[tool.number]) {
    error("Tool T" + tool.number + " is not in the allowed tool list (" + getProperty("allowedTools") + ").");
  }
}

function checkDepth(z) {
  var limit = (stock.uz - stock.lz) + getProperty("maxDepthBelow");
  if (-z > limit + 1e-6) {
    error("Depth " + fmt(-z) + " mm is deeper than stock thickness + " + getProperty("maxDepthBelow") + " mm (" + fmt(limit) + ").");
  }
}

function emitG88(x, y, z, feed) {
  moves.push({kind: "G88", x: x, y: y, z: z, f: feedOut(feed), tool: sectionTool, rpm: sectionRpm});
}

// b lies strictly between a and c, within mergeTolerance of the line a-c.
function collinear(a, b, c) {
  var tol = getProperty("mergeTolerance");
  var acx = c.x - a.x, acy = c.y - a.y, acz = c.z - a.z;
  var abx = b.x - a.x, aby = b.y - a.y, abz = b.z - a.z;
  var len2 = acx * acx + acy * acy + acz * acz;
  if (len2 < 1e-12) {
    return false;
  }
  var t = (abx * acx + aby * acy + abz * acz) / len2;
  if (t <= 0 || t >= 1) {                 // b must lie strictly between a and c: no reversals
    return false;
  }
  var cx = aby * acz - abz * acy, cy = abz * acx - abx * acz, cz = abx * acy - aby * acx;
  return Math.sqrt(cx * cx + cy * cy + cz * cz) / Math.sqrt(len2) <= tol;
}

function addLine(p0, p1, feed) {
  var f = feedOut(feed);
  var last = moves.length ? moves[moves.length - 1] : null;
  if (last && last.kind == "G1" && last.f == f) {
    // Check every point this move already absorbed, not just its end: on a gentle curve
    // (e.g. a linearized arc) checking only the newest point lets the deviation accumulate.
    var between = last.via.concat([last.end]);
    var ok = true;
    for (var i = 0; i < between.length && ok; ++i) {
      ok = collinear(last.start, between[i], p1);
    }
    if (ok) {
      last.via.push(last.end);
      last.end = {x: p1.x, y: p1.y, z: p1.z};
      return;
    }
  }
  moves.push({kind: "G1", start: {x: p0.x, y: p0.y, z: p0.z}, via: [], end: {x: p1.x, y: p1.y, z: p1.z}, f: f});
}

function cut(p0, p1, feed) {
  if (p1.z >= -TOP) {       // retract or move in the air: ends the contour, nothing written
    inContour = false;
    return;
  }
  checkDepth(p1.z);
  var sameXY = Math.abs(p0.x - p1.x) < 1e-4 && Math.abs(p0.y - p1.y) < 1e-4;
  var plunge = sameXY && p1.z < p0.z - 1e-4;   // vertical descent: a new pass, even mid-contour
  if (inContour && !plunge) {
    addLine(p0, p1, feed);
    return;
  }
  if (plunge) {                           // vertical plunge (from the surface, or a stepdown
    emitG88(p1.x, p1.y, p1.z, feed);      // to the next depth without retracting): G88 at the bottom
  } else if (p0.z >= -TOP) {             // ramp from the surface
    emitG88(p0.x, p0.y, 0, feed);
    addLine({x: p0.x, y: p0.y, z: 0}, p1, feed);
  } else {                                // already below the top (e.g. after a rapid at depth)
    emitG88(p0.x, p0.y, p0.z, feed);
    addLine(p0, p1, feed);
  }
  inContour = true;
}

function onRapid(x, y, z) {
  inContour = false;
}

function onLinear(x, y, z, feed) {
  cut(getCurrentPosition(), {x: x, y: y, z: z}, feed);
}

function onCircular(clockwise, cx, cy, cz, x, y, z, feed) {
  var p0 = getCurrentPosition();
  var p1 = {x: x, y: y, z: z};
  if (p1.z >= -TOP) {        // retract or move in the air: ends the contour, nothing written
    inContour = false;       // (checked first: an aerial lead-in/out arc can have an undefined
    return;                  // plane or a Z "helix" that's irrelevant since nothing is cut)
  }
  // A genuine helical entry (Fusion's pocket rampType "helix", spiralling down over many
  // turns) can't be represented by this control's G2/G3 (no Z word) and must be refused.
  // A "profile" ramp (the alternative this message recommends) instead follows the wall,
  // and its corner-rounding arcs can carry a few hundredths of a mm of incidental Z drift
  // while still descending -- that's not a helix; it is linearized below instead.
  var helical = isHelical();
  // getCircularPlane() is only meaningful for a flat arc: a helical one doesn't lie in a
  // single plane by definition (Z moves too), so it reports "undefined" there -- correctly,
  // not an error. Only refuse a genuinely non-XY *flat* arc.
  if (!helical && getCircularPlane() != PLANE_XY) {
    error("Only arcs in the XY plane are supported (operation " + getParameter("operation-comment", "") + ").");
  }
  if (helical && getParameter("operation:rampType", "") != "profile") {
    error("Helical move (helix) in operation " + getParameter("operation-comment", "") +
      ". Set the entry to plunge or ramp (Fusion's pocket default is a helix).");
  }
  // A Z-changing arc (the allowed "profile" ramp case above) can't be written as G2/G3
  // either: that format carries no Z word, so the drop would silently be lost. Linearize
  // it into interpolated-Z chords instead; only a truly flat arc becomes one G2/G3 line.
  if (getProperty("arcOutput") == "lines" || helical) {
    linearizeArc(p0, clockwise, cx, cy, p1, feed);
    return;
  }
  checkDepth(p1.z);
  if (!inContour) {
    emitG88(p0.x, p0.y, p0.z, feed);
    inContour = true;
  }
  moves.push({kind: "ARC", end: p1, r: getCircularRadius(), f: feedOut(feed), cw: clockwise});
}

function linearizeArc(p0, clockwise, cx, cy, p1, feed) {
  var r = Math.sqrt((p0.x - cx) * (p0.x - cx) + (p0.y - cy) * (p0.y - cy));
  var sweep = getCircularSweep();            // radians, positive
  var n = Math.max(1, Math.ceil(r * sweep / getProperty("segmentLength")));
  var a0 = Math.atan2(p0.y - cy, p0.x - cx);
  var dir = clockwise ? -1 : 1;
  var prev = p0;
  for (var i = 1; i <= n; ++i) {
    var a = a0 + dir * sweep * i / n;
    var z = p0.z + (p1.z - p0.z) * i / n;      // interpolate Z along the sweep
    var p = (i == n) ? p1 : {x: cx + r * Math.cos(a), y: cy + r * Math.sin(a), z: z};
    cut(prev, p, feed);
    prev = p;
  }
}

function onSectionEnd() {
  inContour = false;
}

function onCycle() {
  inContour = false;
  if (cycleType != "drilling") {
    error("Drill cycle '" + cycleType + "' is not supported; use plain drilling (drilling - rapid out).");
  }
}

function onCyclePoint(x, y, z) {
  checkDepth(cycle.bottom);
  moves.push({kind: "G81", x: x, y: y, depth: -cycle.bottom, tool: sectionTool});
}

function onCycleEnd() {
}

function formatMoves() {
  var origin = getProperty("origin");
  var out = [];
  var lastF = null;
  var curX = 0, curY = 0, curZ = 0;    // position after the last emitted move (raw, unmirrored)
  for (var i = 0; i < moves.length; ++i) {
    var m = moves[i];
    if (m.kind == "G88") {
      lastF = m.f;
      out.push("G88G90" + origin + "P5T01" + pad2(m.tool) + (m.rpm > 0 ? "S" + Math.round(m.rpm) : "") +
        "F" + fmt(m.f) + "X" + fmt(m.x) + "Y" + fmt(outY(m.y)) + "Z" + fmt(-m.z));
      curX = m.x; curY = m.y; curZ = m.z;
    } else if (m.kind == "G1") {
      var f = (m.f != lastF) ? "F" + fmt(m.f) : "";
      lastF = m.f;
      out.push("G1G90" + f + "X" + fmt(m.end.x) + "Y" + fmt(outY(m.end.y)) + "Z" + fmt(-m.end.z));
      curX = m.end.x; curY = m.end.y; curZ = m.end.z;
    } else if (m.kind == "ARC") {
      if (m.f != lastF) {          // the arc line itself carries no F: announce it first, in place
        out.push("G1G90F" + fmt(m.f) + "X" + fmt(curX) + "Y" + fmt(outY(curY)) + "Z" + fmt(-curZ));
        lastF = m.f;
      }
      var cw = getProperty("mirrorY") ? !m.cw : m.cw;
      out.push((cw ? "G2" : "G3") + "G90G17X" + fmt(m.end.x) + "Y" + fmt(outY(m.end.y)) + "U" + fmt(m.r));
      curX = m.end.x; curY = m.end.y; curZ = m.end.z;
    } else if (m.kind == "G81") {
      out.push("G81G90" + origin + "P5T01" + pad2(m.tool) + "X" + fmt(m.x) + "Y" + fmt(outY(m.y)) + "Z" + fmt(m.depth));
    }
  }
  return out;
}

function onClose() {
  var lines = ["G150(" + progComment + ")"].concat(formatMoves()).concat(["M2"]);
  var n = lines.length + 1;
  var dims = function (v) {
    return fmt(Math.round(v * 100) / 100);
  };
  writeln("G71X" + dims(stock.ux - stock.lx) + "Y" + dims(stock.uy - stock.ly) + "Z" + dims(stock.uz - stock.lz) +
    "T00N" + n + "L" + (n - 3));
  for (var i = 0; i < lines.length; ++i) {
    writeln(lines[i]);
  }
  if (n > getProperty("lineWarning")) {
    warning("Program has " + n + " lines; the largest program this machine is known to run has about 250 lines.");
  }
}
