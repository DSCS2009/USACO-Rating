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
        typ = parseInt(new URLSearchParams(window.location.search).get("type"));
        if (isNaN(typ)) {
            typ = parseInt(readRecordWithExpiry("lastType"));
        }
    } else {
        writeRecordWithExpiry("lastType", typ, 3);
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
    }).fail(function() {
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

function rating2Str(rating, cnt, sd, problemId = null) {
    if (problemId && shouldHideRating(problemId)) {
        return '<td style="color: gray; font-weight: 500;">Hidden</td>';
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
    let showRating = get_circle(rating) + (rating == null ? 'N/A' : Math.round(rating));
    if (sd >= 300) {
        showRating += '<sup style="color: red; font-size: 1em; cursor: pointer;"  data-tooltip="评分标准差过高">*</sup>';
    }
    if (cnt < 10) {
        showRating += '<sup style="color: red; font-size: 1em; cursor: pointer;"  data-tooltip="评分人数过少">*</sup>';
    }
    sd = Math.round(sd * 100) / 100;
    res += `font-weight: 500;" data-position="left center" data-tooltip="Number of votes: ` + cnt + `; σ: ${sd}" data-original-title="" title="">` + showRating + '</td>';
    return res;
}

function quality2Str(quality, cnt, sd, median = false, problemId = null) {
    if (problemId && shouldHideRating(problemId)) {
        return '<td style="color: gray; font-weight: 500;">Hidden</td>';
    }
    var showQuality = Math.round(quality * 100) / 100;
    if (!median) {
        showQuality = showQuality.toFixed(2);
    }
    if (quality <= 0.5) {
        showQuality = "💩 " + showQuality;
    }
    var res = '<td style="';
    if (quality == null) {
        res += 'color: gray;';
        showQuality = "N/A";
    } else {
        if (quality <= 0.5) {
            res += 'color: rgb(157, 108, 73);';
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
    if (sd >= 1.25) {
        showQuality += '<sup style="color: red; font-size: 1em; cursor: pointer;"  data-tooltip="评分标准差过高">*</sup>';
    }
    if (cnt < 10) {
        showQuality += '<sup style="color: red; font-size: 1em; cursor: pointer;"  data-tooltip="评分人数过少">*</sup>';
    }
    sd = Math.round(sd * 10000) / 10000;
    res += `font-weight: 500;" data-position="left center" data-tooltip="Number of votes: ` + cnt + `; σ: ${sd}" data-original-title="" title="">` + showQuality + `</td>`;
    return res;
}

function updateStatus(id) {
    var cur = (getStatus(id) + 1) % 4;
    writeRecord("Status" + id, cur);
    return cur;
}

function statusToColor(status) {
    if (status == 0) return "#FFFFFF";
    if (status == 1) return "#FFEEBA";
    if (status == 2) return "#B8DAFF";
    return "#C3E6CB";
}

function getStatus(id) {
    var res = parseInt(readRecord("Status" + id));
    if (res) {
        return res;
    }
    writeRecord("Status" + id, 0);
    return 0;
}

function render_person (t){
    if (t.id){
        return `<a href="/profile/${t.id}">${t.username || t.name}</a>`
    } else if (t.luoguid){
        return `<a href="https://www.luogu.com.cn/user/${t.luoguid}">${t.username}</a>`
    } else if (t.username) {
        return t.username;
    } else if (t.name) {
        return t.name
    } else {
        return ""
    }
}

function render_source (t){
    if (!t){
        return ""
    }
    if (t.url){
        return `<a href="${t.url}">${t.name}</a>`
    } else if (t.name) {
        return t.name;
    } else {
        return ""
    }
}

function showInfo (id){
    let data = datav[id];
    let ser = data.setter.map(render_person).join("，");
    let sources = data.source.map(render_source).join("，");
    let modal = $.modal({
        title: `Problem - <a href="${data.url}">${data.title}</a>`,
        closeIcon: true,
        content: /*html*/`
            <p>比赛：${data.contest}</p>
            <p>描述：${data.description}</p>
            <p>出题人：${ser || "N/A"}</p>
            <p>来源：${sources || "N/A"}</p>
            <p>通过率： ${data.meta.stats? data.meta.stats.ac_count + "/" + data.meta.stats.submit_count + " (" + (data.meta.stats.ac_count / data.meta.stats.submit_count * 100).toFixed(2) + "%)" : "N/A"}</p>
            <p>平均分： ${data.meta.stats? data.meta.stats.avg_score.toFixed(2) : "N/A"}</p>`,
        classContent: 'content',
    }).modal('show');


}

function display(type) {
    $("#b" + curD).removeClass("active");
    $("#b" + type).addClass("active");
    curD = type;
    var p = $(".problems");
    p.empty();
    for (var i = 0; i < data.length; ++i) {
        var curEntry = data[i];
        // console.log (curEntry)
        // if(curEntry["type"] != type) continue;
        let s = "";
        s += ('<td><strong>' + curEntry["contest"] + '</strong></td>');
        if (practiceMode) {
            s += (`<td id="${curEntry["id"]}p" style="background-color: ${statusToColor(getStatus(curEntry["id"]))}" class="unselectable"  data-tooltip= "${curEntry["description"]}"><a href="${curEntry["url"]}" target="_blank">${curEntry["title"]}</a></td>`);
        } else {
            if (isAdmin) {
                s += (`<td id="${curEntry["id"]}p"  data-tooltip= "${curEntry["description"]}"><a href="${curEntry["url"]}" target="_blank">${curEntry["title"]}</a>    <a class="" onclick="edit(${curEntry["id"]})"> <i class="edit icon"></i> </a> <a class="" onclick="showInfo(${curEntry["id"]})"> <i class="info circle icon"></i> </a> <a href='/problem/${curEntry["id"]}'><i class="external alternate icon"></i></a></td>`);
            } else {
                s += (`<td id="${curEntry["id"]}p"  data-tooltip= "${curEntry["description"]}"><a href="${curEntry["url"]}" target="_blank">${curEntry["title"]}</a>  <a class="" onclick="showInfo(${curEntry["id"]})"> <i class="info circle icon"></i> </a> <a href='/problem/${curEntry["id"]}'><i class="external alternate icon"></i></a></td>`);
            }
        }
        if (useMedian) {
            s += (rating2Str(curEntry["medium_difficulty"], curEntry["cnt1"], curEntry["sd_difficulty"], curEntry["id"]));
            s += (quality2Str(curEntry["medium_quality"], curEntry["cnt2"], curEntry["sd_quality"], true, curEntry["id"]));
        } else {
            s += (rating2Str(curEntry["avg_difficulty"], curEntry["cnt1"], curEntry["sd_difficulty"], curEntry["id"]));
            s += (quality2Str(curEntry["avg_quality"], curEntry["cnt2"], curEntry["sd_quality"], false, curEntry["id"]));
        }
        s += (`<td style="text-align: center;"><a type="button" class="" onclick="vote(${curEntry["id"]})">Vote</a></td>`)
        s += (`<td style="text-align: center;"><a type="button" class="" onclick="showVotes(${curEntry["id"]})">Show Votes</a></td>`)
        p.append('<tr>' + s + '</tr>');
        if (practiceMode) {
            $('#' + curEntry["id"] + 'p').click(function (event) {
                var id = parseInt($(event.target).attr("id").slice(0, -1));
                var status = updateStatus(id);
                $(event.target).css("background-color", statusToColor(status));
            })
        }
        // console.log(p);
    }
    activatePopOver()
    // $("#maint").tablesorter();
}

function monthToValue(s) {
    if (s == "Dec") return 3;
    if (s == "Open") return 2;
    if (s == "Feb") return 1;
    return 0;
}

function sortProblemsCmp(a, b) {
    // if (a["type"] != b["type"]) return a["type"] - b["type"];
    if (sortMode == 0) {
        let aa = a["contest"], bb = b["contest"];
        if (aa > bb) {
            return -1;
        } else if (aa < bb) {
            return 1;
        } else {
            if (a["id"] < b["id"]) {
                return -1;
            }
            return 1;
        }
    } else if (sortMode == 1) {
        var ra = a["avg_difficulty"] == null ? 0 : (useMedian ? a["medium_difficulty"] : a["avg_difficulty"]);
        var rb = b["avg_difficulty"] == null ? 0 : (useMedian ? b["medium_difficulty"] : b["avg_difficulty"]);
        return rb - ra;
    } else {
        var ra = a["avg_quality"] == null ? 0 : (useMedian ? a["medium_quality"] : a["avg_quality"]);
        var rb = b["avg_quality"] == null ? 0 : (useMedian ? b["medium_quality"] : b["avg_quality"]);
        return rb - ra;
    }
}

function sortProblems(type) {
    $("#contest").text("Contest " + (type == 0 ? '▾' : '▴'));
    $("#difficulty").text("Difficulty " + (type == 1 ? '▾' : '▴'));
    $("#quality").text("Quality " + (type == 2 ? '▾' : '▴'));
    sortMode = type;
    data.sort(sortProblemsCmp);
    display(curD);
}

function activatePopOver() {
    // $( "*" ).popup();
}

function vote(id) {
    $.get('/api/queryvote', { "pid": id }, function (res) {
        if (res.error) {
            alert("您暂无资格。");
            return;
        }
        var modal = document.createElement("div");
        let data = res;
        // console.log(data);
        modal.innerHTML = /*html*/`
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
                    <div class="two fields">
                        <div class="field">
                            <label>难度：</label>
                            <input type="text" placeholder="800-3500" value="${data.difficulty}" id="diff">
                        </div>
                        <div class="field">
                            <label>质量：<a class="" type="button" onclick="$('#qual').rating('update', 0);">(设为 0)</a></label>
                            <input type="text" placeholder="1-5" value="${data.quality}" id="qual">
                        </div>
                    </div>
                    <div class="field">
                        <label>评论：</label>
                        <textarea rows="5" id="comment">${data.comment}</textarea>
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
        </div>
        `;
        document.body.appendChild(modal);
        // console.log(modal);
        $('#voteModal').modal('show');
        // destroy on hide
        $('#voteModal').modal({
            onHidden: function () {
                $('#voteModal').remove();
            }
        })
        $('#voteForm').form({
            fields: {
                diff: {
                    identifier: 'diff',
                    rules: [
                        {
                            type: 'empty',
                            prompt: '请输入难度'
                        },
                        {
                            type: 'integer[800..3500]',
                            prompt: '难度范围为 800-3500'
                        }
                    ]
                },
                qual: {
                    identifier: 'qual',
                    rules: [
                        {
                            type: 'empty',
                            prompt: '请输入质量'
                        },
                        {
                            type: 'decimal[0..5]',
                            prompt: '质量范围为 0-5'
                        }
                    ]
                }
            },
            inline: true,
            on: 'blur'
        });
        $('#qual').rating({ 'showClear': false, 'showCaption': false, 'size': 'sm' });
        $('#voteModalSubmit').click(function (event) {
            var diff = parseInt($('#diff').val());
            var qual = parseFloat($('#qual').val());
            var public = $('#public').prop('checked');
            if (!qual) {
                qual = 0
            }
            if (isNaN(diff) || isNaN(qual)) {
                alert("整点阳间输入的吧。");
                return;
            }
            var comment = $('#comment').val();
            if (diff < 800 || diff > 3500 || qual < 0 || qual > 5) {
                alert("输入不合法");
                return;
            }
            $.post('/api/vote', { "pid": id, "diff": diff, "qual": qual, "comment": comment, "public": public }, function (res) {
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
        let data = res;
        // console.log(data);
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
        </div>
        `;
        document.body.appendChild(modal);
        // console.log(modal);
        $('#voteModal').modal('show');
        $('#voteModal').modal({
            onHidden: function () {
                $('#voteModal').remove();
            }
        });
        $('#voteModalSubmit').click(function (event) {
            let contest = $('#contestp').val();
            let title = $('#namep').val();
            let url = $('#urlp').val();
            let des = $('#desp').val();
            let meta = $('#metap').val();
            if (contest == "" || title == "" || url == "" || des == "") {
                alert("输入不合法");
                return;
            }
            $.post('/api/editp', {
                "pid": id,
                "contest": contest,
                "title": title,
                "url": url,
                "des": des,
                "meta": meta
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

function render_list_difficulty(rating, delta) {
    let res = "";
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
    if (quality <= 0.5) {
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
                            <th>难度</th>
                            <th>质量</th>
                            <th>评论</th>
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
                        return `<strong>${row.id}</strong>` + (row.deleted ? " <span style='color: red;'>已删除</span>" : "") + (isAdmin ? `（${row.score}分）` : (row.accepted ? `<i class="check icon" style="color:green"></i>` : ""));
                    }
                },
                {
                    select: 1,
                    render: function (data, type, row) {
                        if (type === 'display') {
                            return render_list_difficulty(row.difficulty, row.difficulty_delta);
                        }
                        return row.difficulty;
                    }
                },
                {
                    select: 2,
                    render: function (data, type, row) {
                        if (type === 'display') {
                            return render_list_quality(row.quality, row.quality_delta);
                        }
                        return row.quality;
                    }
                },
                {
                    select: 3,
                    sortable: false,
                    render: function (data, type, row) {
                        return row.comment;
                    },
                    width: "40%"
                },
                {
                    select: 4,
                    sortable: false,
                    render: function (data, type, row) {
                        if (!isAdmin) {
                            return `<a onclick="report(${row.id})">举报</a>`;
                        } else {
                            return `<a href="/profile/${row.user_id}">${row.username}</a>`;
                        }
                    }
                }
            ]
        });
        modal.modal({
            onShow: function (e) {
                table.draw();
                DataTable.tables({ visible: true, api: true }).columns.adjust();
            },
            onHidden: function (e) {
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