var data = null;
var sortMode = 0;
var curD = 0;
var useMedian = false;
var practiceMode = false;
var hideUnratedRatings = false;
var userVotedProblems = new Set();
var datav = null;

var isAdmin = false;
var nowType = 1;

const knowledgeLevels = [
    "",
    "暂无评定",
    "入门",
    "普及−",
    "普及/提高−",
    "普及+/提高",
    "提高+/省选−",
    "省选/NOI−",
    "NOI/NOI+/CTSC"
];

const knowledgeDifficultyOrder = knowledgeLevels.reduce((acc, level, idx) => {
    acc[level] = idx;
    return acc;
}, {});

function renderKnowledgeTag(value) {
    const label = (value && value.trim()) || "暂无评定";
    const safeLabel = escapeHtml(label);
    return `<span class="knowledge-tag" data-level="${safeLabel}">${safeLabel}</span>`;
}

function renderProblemTags(tags) {
    if (!Array.isArray(tags) || tags.length === 0) {
        return '<span class="problem-tag problem-tag--empty">暂无标签</span>';
    }
    const cleaned = tags
        .filter(tag => tag !== null && tag !== undefined && String(tag).trim() !== '')
        .map(tag => String(tag).trim());
    if (!cleaned.length) {
        return '<span class="problem-tag problem-tag--empty">暂无标签</span>';
    }
    return cleaned
        .map(tag => `<span class="problem-tag">${escapeHtml(tag)}</span>`)
        .join('');
}

function escapeHtml(value) {
    if (value === undefined || value === null) {
        return '';
    }
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function load_announcement() {
    let last_seen = localStorage.getItem("last_seen");
    localStorage.setItem("last_seen", Date.now() / 1000);
    $.get("/api/announcement/newest", function (data) {
        if (data.time > last_seen) {
            $.get("/api/announcements", function (data) {
                data = data.announcements;
                content = ''
                for (let i = 0; i < data.length; i++) {
                    content += `
                <span style="position: relative;">
                    <h2 style="display: inline-block;width: 50%;">${data[i].title}
                    ${data[i].pinned ? '<span style="color:red">[置顶]</span>' : ''}
                    </h2>
                    <small style=" float: right;width: 50%; text-align: right; color: #999;">${TimeUtils.formatTime(data[i].time, 'datetime')}</small>
                </span>
                <div class="description">
                    ${data[i].content}
                </div>
                <div class="ui divider"></div>`
                }
                // console.log(content);
                let modal = `
                <div id ="announcement" class="ui modal">
                    <div class="header">
                        公告
                    </div>
                    <div class="content">
                        ${content}
                    </div>
                    <div class="actions">
                        <div class="ui positive button">确定</div>
                    </div>
                </div>
                `
                $(document.body).append(modal);
                $('#announcement').modal({
                    onHidden: function () {
                        $('#announcement').remove();
                        //console.log("remove");
                    }
                }).modal('show');
            });
        }
    });
}

function init(typ) {
    check_admin();
    load_announcement();
    if (isNaN(typ)) {
        const params = new URLSearchParams(window.location.search);
        const queryType = params.get("type");
        if (queryType !== null) {
            typ = parseInt(queryType);
        }
        if (isNaN(typ)) {
            const cachedType = readRecordWithExpiry("lastType");
            if (cachedType !== null) {
                typ = parseInt(cachedType);
            }
        }
        if (isNaN(typ) && typeof window.__DEFAULT_COURSE_ID__ !== "undefined" && window.__DEFAULT_COURSE_ID__ !== null) {
            typ = parseInt(window.__DEFAULT_COURSE_ID__);
        }
    } else {
        writeRecordWithExpiry("lastType", typ, 3);
    }
    if (isNaN(typ)) {
        typ = 0;
    }

    $.get("/api/problems", { "type": typ }, function (res) {
        data = res.problems;
        datav = {};
        for (let i in data) {
            datav[data[i].id] = data[i];
        }
        typ = res.type;
        if (typ) {
            $("#typename").text(typ.name);
            nowType = typ.id;
        }
        $('#median').bind('change', function () {
            useMedian ^= 1;
            display(curD)
        });
        $('#practice').bind('change', function () {
            practiceMode ^= 1;
            display(curD)
        });
        $('#hideUnrated').bind('change', function () {
            hideUnratedRatings = $('#hideUnrated').is(':checked');
            writeRecord('hideUnratedRatings', hideUnratedRatings);
            if (hideUnratedRatings) {
                loadUserVotes(nowType);
            } else {
                display(curD);
            }
        });

        // Load saved setting
        var savedHideUnrated = readRecord('hideUnratedRatings');
        if (savedHideUnrated === 'true') {
            hideUnratedRatings = true;
            $('#hideUnrated').prop('checked', true);
            loadUserVotes(nowType);
        }

        // $('#practice').prop('checked',true);
        sortProblems(0);
        // displayAnnouncement();
    });
}

function loadUserVotes(typeId) {
    $.get("/api/uservotes", { "type": typeId }, function (res) {
        if (res.error) {
            console.log("Error loading user votes:", res.error);
            hideUnratedRatings = false;
            $('#hideUnrated').prop('checked', false);
            writeRecord('hideUnratedRatings', false);
            return;
        }
        userVotedProblems = new Set(res.voted_problems);
        display(curD);
    }).fail(function () {
        console.log("Failed to load user votes");
        hideUnratedRatings = false;
        $('#hideUnrated').prop('checked', false);
        writeRecord('hideUnratedRatings', false);
    });
}

$(init);


function shouldHideRating(problemId) {
    return hideUnratedRatings && !userVotedProblems.has(problemId);
}

function vote(id) {
    $.get('/api/queryvote', { "pid": id }, function (res) {
        if (res.error) {
            alert("您暂无资格。");
            return;
        }
        const data = res;
        const modalContainer = document.createElement("div");
        modalContainer.innerHTML = /*html*/`
        <div class="ui modal" id="voteModal">
            <i class="inside close icon"></i>
            <div class="header">
                <span id="voteModalTitle">Vote - <a href="${data.url}">${data.title}</a></span>
            </div>
            <div class="content">
                <form class="ui form" id="voteForm">
                    <div class="field">
                        <label>描述：From ${data.contest}；${data.description}</label>
                    </div>
                    <div class="three fields">
                        <div class="field">
                            <label>思维难度</label>
                            <input type="number" min="800" max="3500" value="${data.thinking}" id="think">
                        </div>
                        <div class="field">
                            <label>实现难度</label>
                            <input type="number" min="800" max="3500" value="${data.implementation}" id="impl">
                        </div>
                        <div class="field">
                            <label>质量 (-5 ~ 5)</label>
                            <input type="number" step="0.1" min="-5" max="5" value="${data.quality}" id="qual">
                        </div>
                    </div>
                    <div class="field">
                        <label>评论：</label>
                        <textarea rows="5" id="comment"></textarea>
                    </div>
                </form>
            </div>
            <div class="actions">
                <div class="ui toggle checkbox">
                    <input type="checkbox" id="public">
                    <label for="public">公开评分</label>
                </div>
                <button id="voteModalSubmit" class="ui primary button">提交</button>
            </div>
        </div>`;
        document.body.appendChild(modalContainer);
        $('#comment').val(data.comment || '');
        $('#public').prop('checked', !!data.public);
        $('#voteModal').modal('show');
        $('#voteModal').modal({
            onHidden: function () {
                $('#voteModal').remove();
            }
        });
        $('#voteForm').form({
            fields: {
                think: {
                    identifier: 'think',
                    rules: [
                        { type: 'empty', prompt: '请输入思维难度' },
                        { type: 'integer[800..3500]', prompt: '难度范围为 800-3500' }
                    ]
                },
                impl: {
                    identifier: 'impl',
                    rules: [
                        { type: 'empty', prompt: '请输入实现难度' },
                        { type: 'integer[800..3500]', prompt: '难度范围为 800-3500' }
                    ]
                },
                qual: {
                    identifier: 'qual',
                    optional: true,
                    rules: [
                        {
                            type: 'regExp[/^-?(?:\\d+|\\d*\\.\\d+)$/]',
                            prompt: '请输入有效的浮点数'
                        },
                        {
                            type: 'number[-5..5]',
                            prompt: '质量范围为 -5 到 5'
                        }
                    ]
                }
            },
            inline: true,
            on: 'blur'
        });
        $('#voteModalSubmit').click(function () {
            const think = parseInt($('#think').val());
            const impl = parseInt($('#impl').val());
            const qualRaw = $('#qual').val();
            const qual = qualRaw === '' ? null : parseFloat(qualRaw);
            const isPublic = $('#public').prop('checked');
            const comment = $('#comment').val();
            if (isNaN(think) || isNaN(impl)) {
                alert("请输入有效的难度数值。");
                return;
            }
            if (think < 800 || think > 3500 || impl < 800 || impl > 3500) {
                alert("难度范围为 800-3500");
                return;
            }
            if (qual !== null && (isNaN(qual) || qual < -5 || qual > 5)) {
                alert("质量范围为 -5 到 5");
                return;
            }
            $.post('/api/vote', {
                "pid": id,
                "thinking": think,
                "implementation": impl,
                "quality": qual === null ? '' : qual,
                "comment": comment,
                "public": isPublic
            }, function (res) {
                if (res.success) {
                    alert("投票成功");
                    $('#voteModal').modal('hide');
                    if (hideUnratedRatings) {
                        userVotedProblems.add(id);
                        display(curD);
                    } else {
                        location.reload();
                    }
                } else {
                    alert("投票失败");
                }
            });
        });
    });
}


function render_person(person) {
    if (!person) {
        return '';
    }
    if (person.url) {
        return `<a href="${person.url}">${person.name}</a>`;
    }
    return person.name || '';
}

function render_source(source) {
    if (!source) {
        return '';
    }
    if (source.url) {
        return `<a href="${source.url}">${source.name}</a>`;
    } else if (source.name) {
        return source.name;
    }
    return '';
}

function showInfo(id) {
    const data = datav[id];
    const setterText = (data.setter || []).map(render_person).join('，');
    const sourceText = (data.source || []).map(render_source).join('，');
    const tagList = Array.isArray(data.tags)
        ? data.tags
        : (data.tags ? String(data.tags).split(',').map(item => item.trim()).filter(Boolean) : []);
    const knowledge = data.knowledge_difficulty || (data.meta && data.meta.knowledge_difficulty) || '暂无评定';
    const stats = data.meta && data.meta.stats;
    const passRate = stats && stats.submit_count ? `${stats.ac_count}/${stats.submit_count} (${(stats.ac_count / stats.submit_count * 100).toFixed(2)}%)` : 'N/A';
    const avgScore = stats && stats.avg_score !== undefined ? stats.avg_score.toFixed(2) : 'N/A';
    let modal = $.modal({
        title: `Problem - <a href="${data.url}">${data.title}</a>`,
        closeIcon: true,
        content: /*html*/`
            <p>比赛：${data.contest}</p>
            <p>描述：${data.description}</p>
            <p>知识点难度：${renderKnowledgeTag(knowledge)}</p>
            <p>标签：${renderProblemTags(tagList)}</p>
            <p>出题人：${setterText || 'N/A'}</p>
            <p>来源：${sourceText || 'N/A'}</p>
            <p>通过率： ${passRate}</p>
            <p>平均分： ${avgScore}</p>`,
        classContent: 'content',
    }).modal('show');
}

function display(type) {
    curD = type;
    const container = $(".problems");
    container.empty();
    for (let i = 0; i < data.length; ++i) {
        const curEntry = data[i];
        let cells = `<td><strong>${curEntry.contest}</strong></td>`;
        const metaControl = (isAdmin || curEntry.can_edit_meta) ? ` <a class="" onclick="editMeta(${curEntry.id})"><i class="tags icon"></i></a>` : '';
        if (practiceMode) {
            cells += `<td id="${curEntry.id}p" style="background-color: ${statusToColor(getStatus(curEntry.id))}" class="unselectable" data-tooltip="${curEntry.description}"><a href="${curEntry.url}" target="_blank">${curEntry.title}</a></td>`;
        } else {
            if (isAdmin) {
                const deleteIcon = curEntry.is_custom ? ` <a class="" onclick="deleteProblem(${curEntry.id})"><i class="trash icon" style="color:#db2828"></i></a>` : '';
                cells += `<td id="${curEntry.id}p" data-tooltip="${curEntry.description}"><a href="${curEntry.url}" target="_blank">${curEntry.title}</a> <a class="" onclick="edit(${curEntry.id})"><i class="edit icon"></i></a>${metaControl}${deleteIcon} <a class="" onclick="showInfo(${curEntry.id})"><i class="info circle icon"></i></a> <a href="/problem/${curEntry.id}"><i class="external alternate icon"></i></a></td>`;
            } else {
                cells += `<td id="${curEntry.id}p" data-tooltip="${curEntry.description}"><a href="${curEntry.url}" target="_blank">${curEntry.title}</a>${metaControl} <a class="" onclick="showInfo(${curEntry.id})"><i class="info circle icon"></i></a> <a href="/problem/${curEntry.id}"><i class="external alternate icon"></i></a></td>`;
            }
        }
        const knowledgeValue = curEntry.knowledge_difficulty || (curEntry.meta && curEntry.meta.knowledge_difficulty) || '';
        const tagList = Array.isArray(curEntry.tags)
            ? curEntry.tags
            : (curEntry.tags ? String(curEntry.tags).split(',').map(item => item.trim()).filter(Boolean) : []);
        cells += `<td class="knowledge-cell">${renderKnowledgeTag(knowledgeValue)}</td>`;
        cells += `<td class="tags-cell">${renderProblemTags(tagList)}</td>`;
        const thinkingValue = useMedian ? (curEntry.median_thinking ?? curEntry.avg_thinking) : curEntry.avg_thinking;
        const implementationValue = useMedian ? (curEntry.median_implementation ?? curEntry.avg_implementation) : curEntry.avg_implementation;
        const overallValue = useMedian ? curEntry.medium_difficulty : curEntry.avg_difficulty;
        const qualityValue = useMedian ? curEntry.medium_quality : curEntry.avg_quality;
        cells += rating2Str(thinkingValue, curEntry.cnt_thinking ?? curEntry.cnt1, curEntry.sd_thinking ?? curEntry.sd_difficulty, curEntry.id);
        cells += rating2Str(implementationValue, curEntry.cnt_implementation ?? curEntry.cnt1, curEntry.sd_implementation ?? curEntry.sd_difficulty, curEntry.id);
        cells += rating2Str(overallValue, curEntry.cnt1, curEntry.sd_difficulty, curEntry.id);
        cells += quality2Str(qualityValue, curEntry.cnt2, curEntry.sd_quality, useMedian, curEntry.id);
        cells += `<td style="text-align: center;"><a type="button" onclick="vote(${curEntry.id})">Vote</a></td>`;
        cells += `<td style="text-align: center;"><a type="button" onclick="showVotes(${curEntry.id})">Show Votes</a></td>`;
        container.append('<tr>' + cells + '</tr>');
        if (practiceMode) {
            $('#' + curEntry.id + 'p').click(function (event) {
                const targetId = parseInt($(event.target).attr("id").slice(0, -1));
                const status = updateStatus(targetId);
                $(event.target).css("background-color", statusToColor(status));
            });
        }
    }
    activatePopOver();
}


function editMeta(id) {
    const problem = datav[id];
    const currentTags = (problem.tags || []).join(', ');
    const knowledge = problem.knowledge_difficulty || '';
    const modalNode = document.createElement('div');
    const knowledgeOptions = knowledgeLevels.map(level => {
        const selected = level === (knowledge || '') ? ' selected' : '';
        const label = level === '' ? '清除评定' : level;
        return `<option value="${level}"${selected}>${label}</option>`;
    }).join('');
    modalNode.innerHTML = /*html*/`
    <div class="ui modal" id="metaModal">
        <i class="inside close icon"></i>
        <div class="header">编辑元数据 - ${problem.title}</div>
        <div class="content">
            <form class="ui form" id="metaForm">
                <div class="field">
                    <label>知识点难度</label>
                    <select id="metaKnowledge" class="ui dropdown">
                        ${knowledgeOptions}
                    </select>
                </div>
                <div class="field">
                    <label>标签（逗号分隔）</label>
                    <input type="text" id="metaTags" value="${currentTags}">
                </div>
            </form>
        </div>
        <div class="actions">
            <button id="metaModalSubmit" class="ui primary button">保存</button>
        </div>
    </div>`;
    document.body.appendChild(modalNode);
    $('#metaKnowledge').dropdown();
    $('#metaModal').modal('show');
    $('#metaModal').modal({
        onHidden: function () {
            $('#metaModal').remove();
        }
    });
    $('#metaModalSubmit').click(function () {
        const tagsValue = $('#metaTags').val();
        const knowledgeValue = $('#metaKnowledge').val();
        $.post('/api/problem/meta', {
            pid: id,
            tags: tagsValue,
            knowledge: knowledgeValue
        }, function (res) {
            if (res.success) {
                alert('元数据已更新');
                datav[id].tags = res.tags || [];
                datav[id].knowledge_difficulty = res.knowledge || '';
                for (let i = 0; i < data.length; ++i) {
                    if (data[i].id === id) {
                        data[i].tags = res.tags || [];
                        data[i].knowledge_difficulty = res.knowledge || '';
                        break;
                    }
                }
                $('#metaModal').modal('hide');
            } else {
                alert(res.error || '更新失败');
            }
        });
    });
}


function edit(id) {
    let title = $(`#${id}p a`).text();
    let url = $(`#${id}p a`).attr("href");
    let des = $(`#${id}p`).attr("data-tooltip");
    let contest = $(`#${id}p`).prev().text();
    let meta = datav[id].meta;
    $.get('/api/check', function (res) {
        if (res.error) {
            alert(res.error);
            return;
        }
        var modal = document.createElement("div");
        modal.innerHTML = /*html*/`
        <div class="ui modal" id="voteModal">
            <div class="header">
                <span id="voteModalTitle">更新题目信息</span>
            </div>
            <div class="content">
                <form class="ui form">
                    <div class="two fields">
                        <div class="field">
                            <label for="contest"><strong>比赛：</strong></label>
                            <input type="text" id="contestp" placeholder="" value="${contest}">
                        </div>
                        <div class="field">
                            <label for="name"><strong>题目名：</strong></label>
                            <input type="text" id="namep" placeholder="" value="${title}">
                        </div>
                    </div>
                    <div class="field">
                        <label for="url"><strong>URL：</strong></label>
                        <input type="text" id="urlp" value="${url}">
                    </div>
                    <div class="field">
                        <label for="des"><strong>描述：</strong></label>
                        <input type="text" id="desp" value="${des}">
                    </div>
                    <div class="field">
                        <label for="meta"><strong>Meta：</strong></label>
                        <textarea rows="2" id="metap">${JSON.stringify(meta)}</textarea>
                    </div>
                </form>
            </div>
            <div class="actions">
                <button id="voteModalSubmit" class="ui primary button">提交</button>
            </div>
        </div>`;
        document.body.appendChild(modal);
        $('#voteModal').modal('show');
        $('#voteModal').modal({
            onHidden: function () {
                $('#voteModal').remove();
            }
        });
        $('#voteModalSubmit').click(function () {
            let contestVal = $('#contestp').val();
            let titleVal = $('#namep').val();
            let urlVal = $('#urlp').val();
            let desVal = $('#desp').val();
            let metaVal = $('#metap').val();
            if (contestVal == "" || titleVal == "" || urlVal == "" || desVal == "") {
                alert("输入不合法");
                return;
            }
            $.post('/api/editp', {
                "pid": id,
                "contest": contestVal,
                "title": titleVal,
                "url": urlVal,
                "des": desVal,
                "meta": metaVal
            }, function (res) {
                if (res.success) {
                    alert("修改成功");
                    $('#voteModal').modal('hide');
                    location.reload();
                } else {
                    alert("修改失败");
                }
            });
        });
    });
}

function rating2Str(rating, cnt, sd, problemId = null) {
    if (problemId && shouldHideRating(problemId)) {
        return '<td style="color: gray; font-weight: 500;">Hidden</td>';
    }
    if (rating == null) {
        return '<td style="color: gray; font-weight: 500;">N/A</td>';
    }

    var res = '<td style="';
    if (rating >= 2400) {
        res += 'color: red;';
    } else if (rating >= 2100) {
        res += 'color: rgb(255,140,0);';
    } else if (rating >= 1900) {
        res += 'color: rgb(170,0,170);';
    } else if (rating >= 1600) {
        res += 'color: blue;';
    } else if (rating >= 1400) {
        res += 'color: rgb(3,168,158);';
    } else if (rating >= 1200) {
        res += 'color: green;';
    } else {
        res += 'color: gray;';
    }
    let showRating = get_circle(rating) + Math.round(rating);
    if (sd != null && sd >= 300) {
        showRating += '<sup style="color: red; font-size: 1em; cursor: pointer;"  data-tooltip="评分标准差过高">*</sup>';
    }
    if (cnt < 10) {
        showRating += '<sup style="color: red; font-size: 1em; cursor: pointer;"  data-tooltip="评分人数过少">*</sup>';
    }
    if (sd != null) {
        sd = Math.round(sd * 100) / 100;
    }
    res += `font-weight: 500;" data-position="left center" data-tooltip="Number of votes: ` + cnt + `; σ: ${sd ?? 'N/A'}" data-original-title="" title="">` + showRating + '</td>';
    return res;
}

function quality2Str(quality, cnt, sd, median = false, problemId = null) {
    if (problemId && shouldHideRating(problemId)) {
        return '<td style="color: gray; font-weight: 500;">Hidden</td>';
    }
    var res = '<td style="';
    let showQuality;
    if (quality == null) {
        res += 'color: gray;';
        showQuality = "N/A";
    } else {
        showQuality = Math.round(quality * 100) / 100;
        if (!median) {
            showQuality = showQuality.toFixed(2);
        }
        if (quality <= 0.5) {
            res += 'color: rgb(157, 108, 73);';
            showQuality = "💩 " + showQuality;
        } else if (quality <= 1.5) {
            res += 'color: gray;';
        } else if (quality <= 2.5) {
            res += 'color: rgb(144, 238, 144);';
        } else if (quality <= 3.5) {
            res += 'color: rgb(80, 200, 120);';
        } else if (quality <= 4.5) {
            res += 'color: rgb(34, 139, 34);';
        } else {
            res += 'color: rgb(0, 128, 0);';
        }
    }
    if (sd != null && sd >= 1.25) {
        showQuality += '<sup style="color: red; font-size: 1em; cursor: pointer;"  data-tooltip="评分标准差过高">*</sup>';
    }
    if (cnt < 5) {
        showQuality += '<sup style="color: red; font-size: 1em; cursor: pointer;"  data-tooltip="评分人数过少">*</sup>';
    }
    if (sd != null) {
        sd = Math.round(sd * 100) / 100;
    }
    res += `font-weight: 500;" data-position="left center" data-tooltip="Number of votes: ` + cnt + `; σ: ${sd ?? 'N/A'}" data-original-title="" title="">` + showQuality + '</td>';
    return res;
}

function render_list_difficulty(rating, delta) {
    let res = "";
    if (rating == null) {
        return '<span style="color: gray;">N/A</span>';
    }
    if (rating >= 2400) {
        res += '<span style="color: red;">';
    } else if (rating >= 2100) {
        res += '<span style="color: rgb(255,140,0);">';
    } else if (rating >= 1900) {
        res += '<span style="color: rgb(170,0,170);">';
    } else if (rating >= 1600) {
        res += '<span style="color: blue;">';
    } else if (rating >= 1400) {
        res += '<span style="color: rgb(3,168,158);">';
    } else if (rating >= 1200) {
        res += '<span style="color: green;">';
    } else {
        res += '<span style="color: gray;">';
    }
    let showRating = get_circle(rating) + (rating == null ? 'N/A' : Math.round(rating));
    res += showRating + '</span>';
    // delta = Math.round(delta);
    // if (delta > 0) {
    //     delta = "+" + delta
    // }
    // res += `（${delta}）`;
    return res;

}

function render_list_quality(quality, delta) {
    let res = "";
    if (quality == null) {
        return '<span style="color: gray;">N/A</span>';
    }
    if (quality <= 0.5) {
        res += '<span style="color: rgb(157, 108, 73);">';
    } else if (quality <= 1.5) {
        res += '<span style="color: gray;">';
    } else if (quality <= 2.5) {
        res += '<span style="color: rgb(144, 238, 144);">';
    } else if (quality <= 3.5) {
        res += '<span style="color: rgb(80, 200, 120);">';
    } else if (quality <= 4.5) {
        res += '<span style="color: rgb(34, 139, 34);">';
    } else {
        res += '<span style="color: rgb(0, 128, 0);">';
    }
    let showQuality = Math.round(quality * 100) / 100;
    if (quality <= -4) {
        showQuality = "💩 " + showQuality;
    }
    res += showQuality + '</span>';
    // delta = Math.round(delta * 100) / 100;
    // if (delta > 0) {
    //     delta = "+" + delta
    // }
    // res += `（${delta}）`;
    return res;
}

function deleteVote(id) {
    $.post('/api/delete', { "vid": id }, function (res) {
        if (res.success) {
            alert("删除成功");
        } else {
            alert("删除失败：" + res.error);
        }
    });
}

function deleteProblem(id) {
    if (!confirm("确认删除该题目及其所有评分记录吗？")) {
        return;
    }
    $.post('/api/problem/delete', { "pid": id }, function (res) {
        if (res.success) {
            alert("题目已删除");
            location.reload();
        } else {
            alert("删除失败：" + (res.error || "未知错误"));
        }
    }).fail(function () {
        alert("删除失败：网络错误");
    });
}

function report(id) {
    $.post('/api/report', { "vid": id }, function (res) {
        if (res.success) {
            alert("举报成功");
        } else {
            alert("举报失败：" + res.error);
        }
    });
}

function showVotes(id) {
    $.get('/api/votes', { "pid": id }, function (res) {
        if (res.error) {
            alert("您暂无资格。");
            return;
        }
        let data = res;
        let modal = $.modal({
            title: `Votes - <a href="${data.problem.url}">${data.problem.title}</a>`,
            closeIcon: true,
            content: /*html*/`
                <table class="ui celled table" id="votesTable" style="width:100%">
                    <thead>
                        <tr>
                            <th>编号</th>
                            <th>思维</th>
                            <th>实现</th>
                            <th>综合</th>
                            <th>评论</th>
                            <th>公开</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                    </tbody>
                </table>
            `,
            classContent: 'content',
            class: 'fullscreen',
        }).modal('show');
        let table = new DataTable('#votesTable', {
            sortable: true,
            pageLength: 8,
            lengthChange: false,
            searching: false,
            info: false,
            data: data.votes,
            pagingType: 'simple_numbers',
            columns: [
                {
                    select: 0,
                    render: function (data, type, row) {
                        return `<strong>${row.id}</strong>` + (row.deleted ? " <span style='color: red;'>已删除</span>" : "") + (row.accepted ? `<i class=\"check icon\" style=\"color:green\"></i>` : "") + `<a href="/profile/${row.user_id}">${row.username}</a>`;
                    }
                },
                {
                    select: 1,
                    render: function (data, type, row) {
                        if (type === 'display') {
                            return render_list_difficulty(row.thinking, row.thinking_delta);
                        }
                        return row.thinking;
                    }
                },
                {
                    select: 2,
                    render: function (data, type, row) {
                        if (type === 'display') {
                            return render_list_difficulty(row.implementation, row.implementation_delta);
                        }
                        return row.implementation;
                    }
                },
                {
                    select: 3,
                    render: function (data, type, row) {
                        if (type === 'display') {
                            return render_list_difficulty(row.difficulty, row.difficulty_delta);
                        }
                        return row.difficulty;
                    }
                },
                {
                    select: 4,
                    render: function (data, type, row) {
                        if (type === 'display') {
                            return render_list_quality(row.quality, row.quality_delta);
                        }
                        return row.quality;
                    }
                },
                {
                    select: 5,
                    sortable: false,
                    render: function (data, type, row) {
                        return escapeHtml(row.comment || '').replace(/\n/g, '<br>');
                    },
                    width: "30%"
                },
                {
                    select: 6,
                    sortable: false,
                    render: function (data, type, row) {
                        return row.public ? "是" : "否";
                    }
                },
                {
                    select: 7,
                    sortable: false,
                    render: function (data, type, row) {
                        return `<a onclick=\"report(${row.id})\">举报</a>`;
                    }
                }
            ]
        });
        modal.modal({
            onShow: function () {
                table.draw();
                DataTable.tables({ visible: true, api: true }).columns.adjust();
            },
            onHidden: function () {
                table.destroy();
                modal.remove();
            }
        });
    });
}


function check_admin() {
    $.get('/api/check', function (res) {
        if (!res.error) {
            isAdmin = true;
        }
    });
}

$('.ui.dropdown').dropdown({ action: "select" });

function getMetric(entry, medianKey, avgKey) {
    const medianVal = entry[medianKey];
    const avgVal = entry[avgKey];
    if (useMedian && medianVal !== undefined && medianVal !== null) {
        return medianVal;
    }
    return avgVal;
}

function getKnowledgeSortValue(entry) {
    const knowledge = (entry.knowledge_difficulty || (entry.meta && entry.meta.knowledge_difficulty) || '').trim();
    if (!knowledge) {
        return knowledgeDifficultyOrder['暂无评定'] || 0;
    }
    return knowledgeDifficultyOrder.hasOwnProperty(knowledge) ? knowledgeDifficultyOrder[knowledge] : (knowledgeDifficultyOrder['暂无评定'] || 0);
}

function sortProblemsCmp(a, b) {
    if (sortMode === 0) {
        const ac = a.contest || '';
        const bc = b.contest || '';
        if (ac === bc) {
            return (a.id || 0) - (b.id || 0);
        }
        return bc.localeCompare(ac, 'zh-Hans-CN-u-co-pinyin');
    } else if (sortMode === 1) {
        const ra = getMetric(a, 'median_thinking', 'avg_thinking') || 0;
        const rb = getMetric(b, 'median_thinking', 'avg_thinking') || 0;
        return rb - ra;
    } else if (sortMode === 2) {
        const ra = getMetric(a, 'median_implementation', 'avg_implementation') || 0;
        const rb = getMetric(b, 'median_implementation', 'avg_implementation') || 0;
        return rb - ra;
    } else if (sortMode === 3) {
        const ra = getMetric(a, 'medium_difficulty', 'avg_difficulty') || 0;
        const rb = getMetric(b, 'medium_difficulty', 'avg_difficulty') || 0;
        return rb - ra;
    } else if (sortMode === 4) {
        const ra = getMetric(a, 'medium_quality', 'avg_quality') || 0;
        const rb = getMetric(b, 'medium_quality', 'avg_quality') || 0;
        return rb - ra;
    } else if (sortMode === 5) {
        const ra = getKnowledgeSortValue(a);
        const rb = getKnowledgeSortValue(b);
        if (rb === ra) {
            return (a.id || 0) - (b.id || 0);
        }
        return rb - ra;
    } else {
        return 0;
    }
}

function updateSortHeaders() {
    const headers = [
        { id: '#knowledge', label: '知识点难度', mode: 5 },
        { id: '#thinking', label: '思维难度', mode: 1 },
        { id: '#implementation', label: '实现难度', mode: 2 },
        { id: '#difficulty', label: '综合难度', mode: 3 },
        { id: '#quality', label: '质量', mode: 4 },
    ];
    headers.forEach(({ id, label, mode }) => {
        const arrow = sortMode === mode ? ' ▾' : '';
        $(id).text(label + arrow);
    });
}

function sortProblems(type) {
    sortMode = type;
    updateSortHeaders();
    data.sort(sortProblemsCmp);
    display(curD);
}
