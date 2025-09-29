function writeRecord(name, value) {
    window.localStorage.setItem(name, value);
}

function readRecord(name) {
    return window.localStorage.getItem(name);
}

function removeRecord(name) {
    window.localStorage.removeItem(name);
}

function writeRecordWithExpiry(name, value, hours) {
    const now = new Date().getTime();
    const expires = now + hours * 60 * 60 * 1000;
    const item = {
        value: value,
        expires: expires
    };
    window.localStorage.setItem(name, JSON.stringify(item));
}

function readRecordWithExpiry(name) {
    const itemStr = window.localStorage.getItem(name);
    if (!itemStr) {
        return null;
    }
    const item = JSON.parse(itemStr);
    const now = new Date().getTime();
    if (now > item.expires) {
        window.localStorage.removeItem(name);
        return null;
    }
    return item.value;
}