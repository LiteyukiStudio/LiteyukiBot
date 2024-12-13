// URL
export const OWNER = "LiteyukiStudio"
export const REPO = "LiteyukiBot"
const githubAPIUrl = "https://api.github.com"
const giteaAPIUrl = "https://git.liteyuki.icu/api/v1"
const onlineFetchUrl = "https://api.liteyuki.icu/online";
const totalFetchUrl = "https://api.liteyuki.icu/count";
const visitRecordUrl = "https://api.liteyuki.icu/visit";
const visitCountUrl = "https://api.liteyuki.icu/visit_count";

export const RepoUrl = `https://github.com/${OWNER}/${REPO}`
export const StarMapUrl = "https://starmap.liteyuki.icu"

type GithubStats = {
    stars: number;
    forks: number;
    watchers: number;
    issues?: number;
    prs?: number;
    size?: number;
}

// 异步接口
interface StatsApi {
    getTotal: () => Promise<number>;
    getOnline: () => Promise<number>;
    getGithubStats: () => Promise<GithubStats>;
    getPluginNum: () => Promise<number>;
    getResourceNum: () => Promise<number>;
    getVisitCount: () => Promise<number>;
}


export type {GithubStats};

async function getGiteaStats() {
    try {
        const url = `${giteaAPIUrl}/repos/${OWNER}/${REPO}`;
        console.log(url);
        const res = await fetch(url);
        const data = await res.json();
        return {
            stars: data.stars_count,
            forks: data.forks_count,
            watchers: data.watchers_count,
            issues: 0,
            prs: 0,
            size: data.size,
        };
    } catch (e) {
        return {
            stars: -1,
            forks: -1,
            watchers: -1,
            issues: -1,
            prs: -1,
            size: -1,
        };
    }
}

async function getGithubStats() {
    try {
            const res = await fetch(`${githubAPIUrl}/repos/${OWNER}/${REPO}`);
            const data = await res.json();
            return {
                stars: data.stargazers_count,
                forks: data.forks_count,
                watchers: data.watchers_count,
                issues: data.open_issues_count,
                prs: data.open_issues_count,
                size: data.size,
            };
        } catch (e) {
            return {
                stars: -1,
                forks: -1,
                watchers: -1,
                issues: -1,
                prs: -1,
                size: -1,
            };
        }
}

async function getRepoStats() {
    // 两个接口各数据，加和返回
    const githubStats = await getGithubStats();
    const giteaStats = await getGiteaStats();
    return {
        stars: githubStats.stars + giteaStats.stars,
        forks: githubStats.forks + giteaStats.forks,
        watchers: githubStats.watchers + giteaStats.watchers,
        issues: githubStats.issues + giteaStats.issues,
        prs: githubStats.prs + giteaStats.prs,
        size: githubStats.size + giteaStats.size,
    };
}

// 实现接口
export const statsApi: StatsApi = {
    getTotal: async () => {
        try {
            const res = await fetch(totalFetchUrl);
            const data = await res.json();
            return data.register;
        } catch (e) {
            return -1;
        }
    },
    getOnline: async () => {
        try {
            const res = await fetch(onlineFetchUrl);
            const data = await res.json();
            return data.online;
        } catch (e) {
            return -1;
        }
    },
    getGithubStats: getRepoStats,
    getPluginNum: async () => {
        try {
            const res = await fetch('/plugins.json');
            const data = await res.json();
            return data.length;
        } catch (e) {
            return -1;
        }
    },
    getResourceNum: async () => {
        try {
            const res = await fetch('/resources.json');
            const data = await res.json();
            return data.length;
        } catch (e) {
            return -1;
        }
    },
    getVisitCount: async () => {
        try {
            const res = await fetch(visitCountUrl);
            const data = await res.json();
            return data.count;
        } catch (e) {
            return -1;
        }
    }
};

function getDeviceId(): string {
    // 用户每次访问时生成一个唯一的设备ID，储存在localStorage中，用于统计用户数量
    const deviceIdKey = 'deviceId';
    let deviceId = localStorage.getItem(deviceIdKey);

    if (!deviceId) {
        deviceId = generateUUID();
        localStorage.setItem(deviceIdKey, deviceId);
    }
    return deviceId;
}

export async function uploadVisitRecord() {
    const deviceId = getDeviceId();
    try {
        await fetch(visitRecordUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: new URLSearchParams({'device_id': deviceId}).toString(),
        });
    } catch (e) {
        console.error('Failed to upload visit record:', e);
    }
}

function generateUUID(): string {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = (Math.random() * 16) | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}