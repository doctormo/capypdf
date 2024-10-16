#!/usr/bin/env python3

# Copyright 2023 Jussi Pakkanen
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import unittest
import os, sys, pathlib, shutil, subprocess
import PIL.Image, PIL.ImageChops

if shutil.which('gs') is None:
    sys.exit('Ghostscript not found, test suite can not be run.')

os.environ['CAPYPDF_SO_OVERRIDE'] = 'src' # Sucks, but there does not seem to be a better injection point.
source_root = pathlib.Path(sys.argv[1])
testdata_dir = source_root / 'testoutput'
image_dir = source_root / 'images'
sys.path.append(str(source_root / 'python'))

noto_fontdir = pathlib.Path('/usr/share/fonts/truetype/noto')

sys.argv = sys.argv[0:1] + sys.argv[2:]

import capypdf

def draw_intersect_shape(ctx):
    ctx.cmd_m(50, 90)
    ctx.cmd_l(80, 10)
    ctx.cmd_l(10, 60)
    ctx.cmd_l(90, 60)
    ctx.cmd_l(20, 10)
    ctx.cmd_h()

def validate_image(basename, w, h):
    import functools
    def decorator_validate(func):
        @functools.wraps(func)
        def wrapper_validate(*args, **kwargs):
            assert(len(args) == 1)
            utobj = args[0]
            pngname = pathlib.Path(basename + '.png')
            pdfname = pathlib.Path(basename + '.pdf')
            args = (args[0], pdfname, w, h)
            try:
                pdfname.unlink()
            except Exception:
                pass
            utobj.assertFalse(os.path.exists(pdfname), 'PDF file already exists.')
            value = func(*args, **kwargs)
            the_truth = testdata_dir / pngname
            utobj.assertTrue(os.path.exists(pdfname), 'Test did not generate a PDF file.')
            utobj.assertEqual(subprocess.run(['gs',
                                              '-q',
                                              '-dNOPAUSE',
                                              '-dBATCH',
                                              '-sDEVICE=png16m',
                                              f'-g{w}x{h}',
                                              #'-dPDFFitPage',
                                              f'-sOutputFile={pngname}',
                                              str(pdfname)]).returncode, 0)
            oracle_image = PIL.Image.open(the_truth)
            gen_image = PIL.Image.open(pngname)
            diff = PIL.ImageChops.difference(oracle_image, gen_image)
            utobj.assertFalse(diff.getbbox(), 'Rendered image is different.')
            pdfname.unlink()
            pngname.unlink()
            return value
        return wrapper_validate
    return decorator_validate

def cleanup(ofilename):
    import functools
    def decorator_validate(func):
        @functools.wraps(func)
        def wrapper_validate(*args, **kwargs):
            args = tuple([args[0], ofilename] + list(args)[1:])
            value = func(*args, **kwargs)
            os.unlink(ofilename)
            return value
        return wrapper_validate
    return decorator_validate


class TestPDFCreation(unittest.TestCase):

    @validate_image('python_simple', 480, 640)
    def test_simple(self, ofilename, w, h):
        ofile = pathlib.Path(ofilename)
        with capypdf.Generator(ofile) as g:
            with g.page_draw_context() as ctx:
                ctx.cmd_rg(1.0, 0.0, 0.0)
                ctx.cmd_re(10, 10, 100, 100)
                ctx.cmd_f()

    @validate_image('python_text', 400, 400)
    def test_text(self, ofilename, w, h):
        opts = capypdf.Options()
        opts.set_pagebox(capypdf.PageBox.Media, 0, 0, w, h)
        with capypdf.Generator(ofilename, opts) as g:
            fid = g.load_font(noto_fontdir / 'NotoSans-Regular.ttf')
            with g.page_draw_context() as ctx:
                ctx.render_text('Av, Tv, kerning yo.', fid, 12, 50, 150)

    def test_error(self):
        ofile = pathlib.Path('delme.pdf')
        if ofile.exists():
            ofile.unlink()
        with self.assertRaises(capypdf.CapyPDFException) as cm_outer:
            with capypdf.Generator(ofile) as g:
                ctx = g.page_draw_context()
                with self.assertRaises(capypdf.CapyPDFException) as cm:
                    ctx.cmd_w(-0.1)
                self.assertEqual(str(cm.exception), 'Negative line width.')
                ctx = None # Destroy without adding page, so there should be no output.
        self.assertEqual(str(cm_outer.exception), 'No pages defined.')
        self.assertFalse(ofile.exists())

    def test_line_drawing(self):
        ofile = pathlib.Path('nope.pdf')
        with capypdf.Generator(ofile) as g:
            with g.page_draw_context() as ctx:
                ctx.cmd_J(capypdf.LineCapStyle.Round)
                ctx.cmd_j(capypdf.LineJoinStyle.Bevel)
        ofile.unlink()

    @validate_image('python_image', 200, 200)
    def test_images(self, ofilename, w, h):
        opts = capypdf.Options()
        opts.set_pagebox(capypdf.PageBox.Media, 0, 0, w, h)
        with capypdf.Generator(ofilename, opts) as g:
            bg_img = g.embed_jpg(image_dir / 'simple.jpg')
            mono_img = g.load_image(image_dir / '1bit_noalpha.png')
            gray_img = g.load_image(image_dir / 'gray_alpha.png')
            rgb_tif_img = g.load_image(image_dir / 'rgb_tiff.tif')
            with g.page_draw_context() as ctx:
                with ctx.push_gstate():
                    ctx.translate(10, 10)
                    ctx.scale(80, 80)
                    ctx.draw_image(bg_img)
                with ctx.push_gstate():
                    ctx.translate(0, 100)
                    ctx.translate(10, 10)
                    ctx.scale(80, 80)
                    ctx.draw_image(mono_img)
                with ctx.push_gstate():
                    ctx.translate(110, 110)
                    ctx.scale(80, 80)
                    ctx.draw_image(gray_img)
                with ctx.push_gstate():
                    ctx.translate(110, 10)
                    ctx.scale(80, 80)
                    ctx.draw_image(rgb_tif_img)

    @validate_image('python_path', 200, 200)
    def test_path(self, ofilename, w, h):
        opts = capypdf.Options()
        opts.set_pagebox(capypdf.PageBox.Media, 0, 0, w, h)
        with capypdf.Generator(ofilename, opts) as g:
            with g.page_draw_context() as ctx:
                with ctx.push_gstate():
                    ctx.cmd_w(5)
                    ctx.cmd_J(capypdf.LineCapStyle.Round)
                    ctx.cmd_m(10, 10);
                    ctx.cmd_c(80, 10, 20, 90, 90, 90);
                    ctx.cmd_S();
                with ctx.push_gstate():
                    ctx.cmd_w(10)
                    ctx.translate(100, 0)
                    ctx.cmd_RG(1.0, 0.0, 0.0)
                    ctx.cmd_rg(0.9, 0.9, 0.0)
                    ctx.cmd_j(capypdf.LineJoinStyle.Bevel)
                    ctx.cmd_m(50, 90)
                    ctx.cmd_l(10, 10)
                    ctx.cmd_l(90, 10)
                    ctx.cmd_h()
                    ctx.cmd_B()
                with ctx.push_gstate():
                    ctx.translate(0, 100)
                    draw_intersect_shape(ctx)
                    ctx.cmd_w(3)
                    ctx.cmd_rg(0, 1, 0)
                    ctx.cmd_RG(0.5, 0.1, 0.5)
                    ctx.cmd_j(capypdf.LineJoinStyle.Round)
                    ctx.cmd_B()
                with ctx.push_gstate():
                    ctx.translate(100, 100)
                    ctx.cmd_w(2)
                    ctx.cmd_rg(0, 1, 0);
                    ctx.cmd_RG(0.5, 0.1, 0.5)
                    draw_intersect_shape(ctx)
                    ctx.cmd_Bstar()

    @validate_image('python_textobj', 200, 200)
    def test_text(self, ofilename, w, h):
        opts = capypdf.Options()
        opts.set_pagebox(capypdf.PageBox.Media, 0, 0, w, h)
        with capypdf.Generator(ofilename, opts) as g:
            font = g.load_font(noto_fontdir / 'NotoSerif-Regular.ttf')
            with g.page_draw_context() as ctx:
                t = ctx.text_new()
                t.cmd_Tf(font, 12.0)
                t.cmd_Td(10.0, 100.0)
                t.render_text('Using text object!')
                ctx.render_text_obj(t)

    @validate_image('python_icccolor', 200, 200)
    def test_icc(self, ofilename, w, h):
        opts = capypdf.Options()
        opts.set_pagebox(capypdf.PageBox.Media, 0, 0, w, h)
        with capypdf.Generator(ofilename, opts) as g:
            cs = g.load_icc_profile('/usr/share/color/icc/colord/AdobeRGB1998.icc')
            sc = capypdf.Color()
            sc.set_icc(cs, [0.1, 0.2, 0.8])
            nsc = capypdf.Color()
            nsc.set_icc(cs, [0.7, 0.2, 0.6])
            with g.page_draw_context() as ctx:
                ctx.set_stroke(sc)
                ctx.set_nonstroke(nsc)
                ctx.cmd_w(2)
                ctx.cmd_re(10, 10, 80, 80)
                ctx.cmd_B()

    @cleanup('transitions.pdf')
    def test_transitions(self, ofilename):
        opts = capypdf.Options()
        opts.set_pagebox(capypdf.PageBox.Media, 0, 0, 160, 90)
        with capypdf.Generator(ofilename, opts) as g:
            with g.page_draw_context() as ctx:
                pass
            with g.page_draw_context() as ctx:
                tr = capypdf.Transition(capypdf.TransitionType.Blinds, 1.0)
                ctx.set_page_transition(tr)
                ctx.cmd_rg(0.5, 0.5, 0.5)
                ctx.cmd_re(0, 0, 160, 90)
                ctx.cmd_f()


if __name__ == "__main__":
    unittest.main()
