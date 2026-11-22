// Project files for custom components (20.10 item 26).
// A component names a file of its project as the file name, e.g. mediaUrl('media/octo.png').
// ARGUS links every such file into the job's public dir under m/<key> before the render, and this
// helper maps the name to that path. The key rule must match `_media_key` in
// src/argus/tools/render.py: every character outside [A-Za-z0-9._-] becomes "_".
import {resolveMedia} from '../style';

const mediaKey = (name: string): string => name.replace(/[^A-Za-z0-9._-]/g, '_');

export const mediaUrl = (name: string): string => resolveMedia(`m/${mediaKey(name)}`);
