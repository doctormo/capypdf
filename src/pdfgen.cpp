/*
 * Copyright 2022 Jussi Pakkanen
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <pdfgen.hpp>
#include <cstring>
#include <cerrno>
#include <cassert>
#include <lcms2.h>
#include <iconv.h>
#include <stdexcept>
#include <array>
#include <fmt/core.h>
#include <ft2build.h>
#include FT_FREETYPE_H
#include FT_FONT_FORMATS_H
#include FT_OPENTYPE_VALIDATE_H

namespace A4PDF {

LcmsHolder::~LcmsHolder() { deallocate(); }

void LcmsHolder::deallocate() {
    if(h) {
        cmsCloseProfile(h);
    }
    h = nullptr;
}

DrawContextPopper::~DrawContextPopper() {
    switch(ctx.draw_context_type()) {
    case A4PDF_Page_Context:
        g->add_page(ctx);
        break;
    default:
        std::abort();
    }
}

PdfGen::PdfGen(const char *ofname, const PdfGenerationData &d) : ofilename(ofname), pdoc{d} {
    auto error = FT_Init_FreeType(&ft);
    if(error) {
        throw std::runtime_error(FT_Error_String(error));
    }
}

PdfGen::~PdfGen() {
    pdoc.font_objects.clear();
    pdoc.fonts.clear();
    auto error = FT_Done_FreeType(ft);
    if(error) {
        fprintf(stderr, "Closing FreeType failed: %s\n", FT_Error_String(error));
    }
}

ErrorCode PdfGen::write() {
    if(pdoc.pages.size() == 0) {
        return ErrorCode::NoPages;
    }

    std::string tempfname = ofilename.c_str();
    tempfname += "~";
    FILE *ofile = fopen(tempfname.c_str(), "wb");
    if(!ofile) {
        perror(nullptr);
        return ErrorCode::CouldNotOpenFile;
    }

    try {
        pdoc.write_to_file(ofile);
    } catch(const std::exception &e) {
        fprintf(stderr, "%s", e.what());
        fclose(ofile);
        return ErrorCode::DynamicError;
    } catch(...) {
        fprintf(stderr, "Unexpected error.\n");
        fclose(ofile);
        return ErrorCode::DynamicError;
    }

    if(fflush(ofile) != 0) {
        perror(nullptr);
        fclose(ofile);
        return ErrorCode::DynamicError;
    }
    if(fsync(fileno(ofile)) != 0) {
        perror(nullptr);
        fclose(ofile);
        return ErrorCode::FileWriteError;
    }
    if(fclose(ofile) != 0) {
        perror(nullptr);
        return ErrorCode::FileWriteError;
    }

    // If we made it here, the file has been fully written and fsynd'd to disk. Now replace.
    if(rename(tempfname.c_str(), ofilename.c_str()) != 0) {
        perror(nullptr);
        return ErrorCode::FileWriteError;
    }
    return ErrorCode::NoError;
}

PageId PdfGen::add_page(PdfDrawContext &ctx) {
    if(ctx.draw_context_type() != A4PDF_Page_Context) {
        throw std::runtime_error("Tried to pass a non-page context to add_page.");
    }
    auto sc = ctx.serialize();
    pdoc.add_page(std::move(sc.dict), std::move(sc.commands));
    ctx.clear();
    return PageId{(int32_t)pdoc.pages.size() - 1};
}

PatternId PdfGen::add_pattern(ColorPatternBuilder &cp) {
    if(cp.pctx.draw_context_type() != A4PDF_Color_Tiling_Pattern_Context) {
        throw std::runtime_error("Tried to pass an incorrect pattern type to add_pattern.");
    }
    auto resources = cp.pctx.build_resource_dict();
    auto commands = cp.pctx.get_command_stream();
    auto buf = fmt::format(R"(<<
  /Type /Pattern
  /PatternType 1
  /PaintType 1
  /TilingType 1
  /BBox [ {} {} {} {}]
  /XStep {}
  /YStep {}
  /Resources {}
  /Length {}
>>
)",
                           0,
                           0,
                           cp.w,
                           cp.h,
                           cp.w,
                           cp.h,
                           resources,
                           commands.length());

    return pdoc.add_pattern(buf, commands);
}

DrawContextPopper PdfGen::guarded_page_context() {
    return DrawContextPopper{this, &pdoc, &pdoc.cm, A4PDF_Page_Context};
}

PdfDrawContext *PdfGen::new_page_draw_context() {
    return new PdfDrawContext{&pdoc, &pdoc.cm, A4PDF_Page_Context};
}

ColorPatternBuilder PdfGen::new_color_pattern_builder(double w, double h) {
    return ColorPatternBuilder{
        PdfDrawContext{&pdoc, &pdoc.cm, A4PDF_Color_Tiling_Pattern_Context}, w, h};
}

double PdfGen::utf8_text_width(const char *utf8_text, A4PDF_FontId fid, double pointsize) const {
    double w = 0;
    errno = 0;
    auto to_codepoint = iconv_open("UCS-4LE", "UTF-8");
    if(errno != 0) {
        throw std::runtime_error(strerror(errno));
    }
    std::unique_ptr<void, int (*)(void *)> iconvcloser(to_codepoint, iconv_close);
    FT_Face face = pdoc.fonts.at(pdoc.font_objects.at(fid.id).font_index_tmp).fontdata.face.get();
    if(!face) {
        throw std::runtime_error(
            "Tried to use builtin font to render UTF-8. They only support ASCII.");
    }

    uint32_t previous_codepoint = -1;
    auto in_ptr = (char *)utf8_text;
    const auto text_length = strlen(utf8_text);
    auto in_bytes = text_length;
    // Freetype does not support GPOS kerning because it is context-sensitive.
    // So this method might produce incorrect kerning. Users that need precision
    // need to use the glyph based rendering method.
    const bool has_kerning = FT_HAS_KERNING(face);
    if(has_kerning) {
        printf("HAS KERNING\n");
    }
    while(in_bytes > 0) {
        uint32_t codepoint{0};
        auto out_ptr = (char *)&codepoint;
        auto out_bytes = sizeof(codepoint);
        errno = 0;
        auto iconv_result = iconv(to_codepoint, &in_ptr, &in_bytes, &out_ptr, &out_bytes);
        if(iconv_result == (size_t)-1 && errno != E2BIG) {
            throw std::runtime_error(strerror(errno));
        }
        if(has_kerning && previous_codepoint != (uint32_t)-1) {
            FT_Vector kerning;
            const auto index_left = FT_Get_Char_Index(face, previous_codepoint);
            const auto index_right = FT_Get_Char_Index(face, codepoint);
            auto ec = FT_Get_Kerning(face, index_left, index_right, FT_KERNING_DEFAULT, &kerning);
            if(ec != 0) {
                throw std::runtime_error("Getting kerning data failed.");
            }
            if(kerning.x != 0) {
                // None of the fonts I tested had kerning that Freetype recognized,
                // so don't know if this actually works.
                w += int(kerning.x) / face->units_per_EM;
            }
        }
        auto bob = glyph_advance(fid, pointsize, codepoint);
        assert(bob);
        w += *bob;
        previous_codepoint = codepoint;
    }
    return w;
}

} // namespace A4PDF
