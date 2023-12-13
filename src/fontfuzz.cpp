/*
 * Copyright 2023 Jussi Pakkanen
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

#include <ft_subsetter.hpp>
#include <string_view>
#include <stdexcept>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *buf, size_t bufsize) {
    if(!buf) {
        return 0;
    }
    try {
        auto font = capypdf::parse_truetype_font(std::string_view((const char *)buf, bufsize));
    } catch(const std::runtime_error &) {
    }

    return 0;
}
