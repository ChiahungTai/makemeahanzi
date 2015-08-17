#!/usr/bin/python
'''
Extracts one or more characters from each of the svg fonts in the SVG directory
and packages them into a 'chars.html' output file.
'''
import math
import os
import svg.path
import sys

SCALE = 0.16
SVG_DIR = 'derived'
TRANSFORM = 'scale({0:.2g}, -{0:0.2g}) translate(0, -900)'.format(SCALE)

# Constants controlling our stroke extraction algorithm.
MAX_CROSSING_DISTANCE = 64
MAX_CUSP_MERGE_DISTANCE = 15
MIN_CUSP_ANGLE = 0.1*math.pi


class Cusp(object):
  def __init__(self, paths, index):
    self.paths = paths
    self.index = index
    (i, j) = index
    self.point = paths[i][j].end
    (self.tangent1, self.tangent2) = self._get_tangents(self.paths[i], j)
    self.angle = self._get_angle(self.tangent1, self.tangent2)

  def connect(self, other):
    # Returns true if a troke continues from this cusp point to the other.
    if other.index == self.index:
      return False
    if other.index[0] == self.index[0]:
      return self._try_connect(other)
    return self._try_connect(other) or self._try_connect(other, True)

  def merge(self, other):
    # Returns true if this cusp point is close enough to the next one that
    # they should be combined into one cusp point. If this method returns
    # true, other will be populated with the merged cusp data.
    assert other.index[0] == self.index[0], 'merge called for different paths!'
    if abs(other.point - self.point) > MAX_CUSP_MERGE_DISTANCE:
      return False
    distance = 0
    j = self.index[1]
    path = self.paths[self.index[0]]
    while j != other.index[1]:
      j = (j + 1) % len(path)
      distance += abs(path[j].end - path[j].start)
    if distance > MAX_CUSP_MERGE_DISTANCE:
      return False
    # We should merge. Check which point is the real cusp and update other.
    if abs(self.angle) > abs(other.angle):
      other.index = self.index
      other.point = self.point
    other.tangent1 = self.tangent1
    other.angle = other._get_angle(other.tangent1, other.tangent2)
    return True

  def _get_angle(self, vector1, vector2):
    if not vector1 or not vector2:
      return 0
    ratio = vector1/vector2
    return math.atan2(ratio.imag, ratio.real)

  def _get_tangents(self, path, index):
    segment1 = path[index]
    tangent1 = segment1.end - segment1.start
    if (type(segment1) == svg.path.QuadraticBezier and
        segment1.end != segment1.control):
      tangent1 = segment1.end - segment1.control
    segment2 = path[(index + 1) % len(path)]
    tangent2 = segment2.end - segment2.start
    if (type(segment2) == svg.path.QuadraticBezier and
        segment2.control != segment2.end):
      tangent2 = segment2.control - segment2.start
    return (tangent1, tangent2)

  def _try_connect(self, other, reverse=False):
    if other.point == self.point:
      return True
    diff = other.point - self.point
    length = abs(diff)
    if length > MAX_CROSSING_DISTANCE:
      return False
    (other1, other2) = (other.tangent1, other.tangent2)
    if reverse:
      (other1, other2) = (other2, other1)
    features = (
      self._get_angle(self.tangent1, diff),
      self._get_angle(diff, other2),
      self._get_angle(diff, self.tangent2),
      self._get_angle(other1, diff),
      length,
    )
    # TODO(skishore): Replace this set of inequalities with a machine-learned
    # classifier such as a neural net.
    result = (features[2]*features[3] > 0 and
              abs(features[0]) < 0.3*math.pi and
              abs(features[1]) < 0.3*math.pi and
              abs(features[2]) > 0.3*math.pi and
              abs(features[3]) > 0.3*math.pi)
    print (self.point, other.point, features, int(result))
    return result


def augment_glyph(glyph):
  names = [token for token in glyph.split() if 'glyph-name' in token]
  print '\n#{0}'.format(names[0] if names else 'glyph-name="unknown"')
  path = svg.path.parse_path(get_svg_path_data(glyph))
  path = svg.path.Path(
      *[element for element in path if element.start != element.end])
  assert path, 'Got empty path for glyph:\n{0}'.format(glyph)
  paths = break_path(path)
  cusps = get_cusps(paths)
  # Actually augment the glyph with stroke-aligned cuts.
  result = []
  for cusp in cusps:
    result.append(
        '<circle cx="{0}" cy="{1}" r="4" fill="red" stroke="red" '
        'data-angle="{2}"/>'.format(
            int(cusp.point.real), int(cusp.point.imag), cusp.angle))
  for cusp in cusps:
    for other in cusps:
      if cusp.connect(other):
        result.append(
            '<line x1="{0}" y1="{1}" x2="{2}" y2="{3}" style="{4}"/>'.format(
                int(cusp.point.real), int(cusp.point.imag),
                int(other.point.real), int(other.point.imag),
                'stroke:white;stroke-width:8'))
  return result

def break_path(path):
  subpaths = [[path[0]]]
  for element in path[1:]:
    if element.start != subpaths[-1][-1].end:
      subpaths.append([])
    subpaths[-1].append(element)
  return [svg.path.Path(*subpath) for subpath in subpaths]

def get_cusps(paths):
  result = []
  for i, path in enumerate(paths):
    cusps = []
    for j, element in enumerate(path):
      cusp = Cusp(paths, (i, j))
      if abs(cusp.angle) > MIN_CUSP_ANGLE:
        cusps.append(cusp)
    j = 0
    while j < len(cusps):
      if cusps[j].merge(cusps[(j + 1) % len(cusps)]):
        cusps.pop(j)
      else:
        j += 1
    result.extend(cusps)
  return result

def get_svg_path_data(glyph):
  left = ' d="'
  start = max(glyph.find(left), glyph.find(left.replace(' ', '\n')))
  assert start >= 0, 'Glyph missing d=".*" block:\n{0}'.format(repr(glyph))
  end = glyph.find('"', start + len(left))
  assert end >= 0, 'Glyph missing d=".*" block:\n{0}'.format(repr(glyph))
  return glyph[start + len(left):end].replace('\n', ' ')


if __name__ == '__main__':
  assert len(sys.argv) > 1, 'Usage: ./getchar.py <unicode_codepoint>+'
  svgs = [file_name for file_name in os.listdir(SVG_DIR)
          if file_name.endswith('.svg') and not file_name.startswith('.')]
  glyphs = []
  for file_name in svgs:
    glyphs.append([])
    with open(os.path.join(SVG_DIR, file_name)) as file:
      data = file.read()
    for codepoint in sys.argv[1:]:
      index = data.find('unicode="&#x{0};"'.format(codepoint))
      if index < 0:
        print >> sys.stderr, '{0}: missing {1}'.format(file_name, codepoint)
        continue
      (left, right) = ('<glyph', '/>')
      (start, end) = (data.rfind(left, 0, index), data.find(right, index))
      if start < 0 or end < 0:
        print >> sys.stderr, '{0}: malformed {1}'.format(file_name, codepoint)
        continue
      glyphs[-1].append(data[start:end + len(right)])

  with open('chars.html', 'w') as f:
    f.write('<!DOCTYPE html>\n  <html>\n    <body>\n')
    for row in glyphs:
      f.write('      <div>\n')
      for glyph in row:
        size = int(1024*SCALE)
        f.write('        <svg width="{0}" height="{0}">\n'.format(size))
        f.write('          <g transform="{0}">\n'.format(TRANSFORM))
        f.write(glyph.replace('<glyph', '<path'))
        for extra in augment_glyph(glyph):
          f.write(extra)
        f.write('          </g>\n')
        f.write('        </svg>\n')
      f.write('      </div>\n')
    f.write('    </body>\n  </html>')
