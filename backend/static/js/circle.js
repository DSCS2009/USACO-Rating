// code from kira924age/CodeforcesProblems

// MIT License
//
// Copyright (c) 2022 kira924age
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

function getColor(difficulty) {
    let color;

    if (difficulty === undefined) {
        color = "black";
    } else if (difficulty < 1200) {
        color = "grey";
    } else if (difficulty < 1400) {
        color = "green";
    } else if (difficulty < 1600) {
        color = "cyan";
    } else if (difficulty < 1900) {
        color = "blue";
    } else if (difficulty < 2100) {
        color = "violet";
    } else if (difficulty < 2400) {
        color = "orange";
    } else if (difficulty < 3000) {
        color = "red";
    } else if (difficulty < 3200) {
        color = "bronze";
    } else if (difficulty < 3400) {
        color = "silver";
    } else {
        color = "gold";
    }

    return color;
}

function getColorCode(difficulty, theme="") {
    let color;

    if (difficulty < 1200) {
        color = theme === "dark" ? "#C0C0C0" : "#808080";
    } else if (difficulty < 1400) {
        color = theme === "dark" ? "#3FAF3F" : "#008000";
    } else if (difficulty < 1600) {
        color = theme === "dark" ? "#42E0E0" : "#03A89E";
    } else if (difficulty < 1900) {
        color = theme === "dark" ? "#8888FF" : "#0000FF";
    } else if (difficulty < 2100) {
        color = theme === "dark" ? "#BA55D3" : "#AA00AA";
    } else if (difficulty < 2400) {
        color = "#FF8C00";
    } else if (difficulty < 3000) {
        color = theme === "dark" ? "#FF375F" : "#FF0000";
    } else if (difficulty < 3200) {
        color = "#965C2C";
    } else if (difficulty < 3400) {
        color = "#808080";
    } else {
        color = "#FFD700";
    }

    return color;
}

function calcFillRatio(difficulty) {
    let fillRatio = 0;

    if (difficulty < 1200) {
        fillRatio = (difficulty - 800) / 400;
    } else if (difficulty < 1400) {
        fillRatio = 1 - (1400 - difficulty) / 200;
    } else if (difficulty < 1600) {
        fillRatio = 1 - (1600 - difficulty) / 200;
    } else if (difficulty < 1900) {
        fillRatio = 1 - (1900 - difficulty) / 300;
    } else if (difficulty < 2100) {
        fillRatio = 1 - (2100 - difficulty) / 200;
    } else if (difficulty < 2400) {
        fillRatio = 1 - (2400 - difficulty) / 300;
    } else if (difficulty < 3000) {
        fillRatio = 1 - (3000 - difficulty) / 600;
    } else {
        fillRatio = 1.0;
    }
    return fillRatio;
}


function get_circle(rating) {
    const color = getColor(rating);
    const theme = ''
    const colorCode = getColorCode(rating, theme);
    const fillRatio = calcFillRatio(rating);

    const isMetal = color === "bronze" || color === "silver" || color === "gold";
    // console.log(isMetal,color);
    let metalOption = {
        base: "", highlight: "",
    };
    if (color === "bronze") {
        metalOption = {base: "#965C2C", highlight: "#FFDABD"};
    }
    if (color === "silver") {
        metalOption = {base: "#808080", highlight: "white"};
    }
    if (color === "gold") {
        metalOption = {base: "#FFD700", highlight: "white"};
    }

    const styles = isMetal ? {
        'border-color': colorCode, background: `linear-gradient(to right, \
        ${metalOption.base}, ${metalOption.highlight}, ${metalOption.base})`, color: colorCode,
    } : {
        'border-color': colorCode, 'border-style': "solid", background: `linear-gradient(to top, \
        ${colorCode} 0%, \
        ${colorCode} ${fillRatio * 100}%, \
        rgba(0,0,0,0) ${fillRatio * 100}%, \
        rgba(0,0,0,0) 100%)`, color: colorCode,
    };
    return `<span
        class="difficulty-circle"
        style="${Object.entries(styles).map(([k, v]) => `${k}: ${v};`).join('')}"
    ></span>`;
}
