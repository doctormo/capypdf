#!/usr/bin/env python3

import pathlib, os, sys

os.environ['CAPYPDF_SO_OVERRIDE'] = 'src'
source_root = pathlib.Path(__file__).parent / '..'
sys.path.append(str(source_root / 'python'))

import capypdf

def cm2pt(pts):
    return pts*28.346;

class BulletPage:
    def __init__(self, title, entries):
        self.title = title
        self.entries = entries

def create_pages():
    pages = [BulletPage('This is a heading', ['Bullet point 1',
                                              'Bullet point 2',
                                              'The third entry is so long that it overflows and takes two lines.'])]
    return pages

class Demopresentation:
    def __init__(self, ofilename, w, h):
        self.ofilename = ofilename
        self.w = w
        self.h = h
        self.fontfile = '/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf'
        self.boldfontfile = '/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf'
        self.symbolfontfile = '/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf'
        self.headingsize = 44
        self.textsize = 32
        self.symbolsize = 28
        opts = capypdf.Options()
        opts.set_author('CapyPDF tester')
        opts.set_pagebox(capypdf.PageBox.Media, 0, 0, w, h)
        self.pdfgen = capypdf.Generator(self.ofilename, opts)
        self.basefont = self.pdfgen.load_font(self.fontfile)
        self.boldbasefont = self.pdfgen.load_font(self.boldfontfile)
        self.symbolfont = self.pdfgen.load_font(self.symbolfontfile)

    def split_to_lines(self, text, fid, ptsize, width):
        if self.pdfgen.text_width(text, fid, ptsize) <= width:
            return [text]
        words = text.strip().split(' ')
        lines = []
        space_width = self.pdfgen.text_width(' ', fid, ptsize)
        current_line = []
        current_width = 0
        for word in words:
            wwidth = self.pdfgen.text_width(word, fid, ptsize)
            if current_width + space_width + wwidth >= width:
                lines.append(' '.join(current_line))
                current_line = [word]
                current_width = wwidth
            else:
                current_line.append(word)
                current_width += space_width + wwidth
        if current_line:
            lines.append(' '.join(current_line))
        return lines

    def render_bullet_page(self, ctx, p):
        text_w = self.pdfgen.text_width(p.title, self.boldbasefont, self.headingsize)
        head_y = self.h - 1.5*self.headingsize
        ctx.render_text(p.title, self.boldbasefont, self.headingsize, (self.w-text_w)/2, head_y)
        current_y = head_y - 1.5*self.headingsize
        box_indent = 90
        bullet_separation = 1.5
        bullet_linesep = 1.2
        for entry in p.entries:
            ctx.render_text('🞂', self.symbolfont, self.symbolsize, box_indent - 40, current_y+1)
            for line in self.split_to_lines(entry, self.basefont, self.textsize, self.w - 2*box_indent):
                ctx.render_text(line, self.basefont, self.textsize, box_indent, current_y)
                current_y -= bullet_linesep*self.textsize
            current_y += (bullet_linesep - bullet_separation)*self.textsize

    def add_pages(self, pages):
        for page in pages:
            with self.pdfgen.page_draw_context() as ctx:
                if isinstance(page, BulletPage):
                    self.render_bullet_page(ctx, page)
                else:
                    raise RuntimeError('Unknown page type.')

    def finish(self):
        self.pdfgen.write()

if __name__ == '__main__':
    p = Demopresentation('demo_presentation.pdf', cm2pt(28), cm2pt(16))
    pages = create_pages()
    p.add_pages(pages)
    p.finish()
