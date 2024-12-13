// 本模块储存一些工具函数和引用

/**
 * GetEditLink Options
 * @param text Edit link text
 */
export const ThemeConfig = {
    getEditLink: (editPageText: string): { pattern: (params: { filePath: string; }) => string; text: string; } => {
        return {
            pattern: ({filePath}: { filePath: string; }): string => {
                // 匹配 /dev/api或 /{lang}/dev/api
                const regex = /^[^\/]+\/dev\/api/;
                console.log(filePath);
                if (regex.test(filePath)) {
                    // remove {lang}/api prefix
                    filePath = filePath.replace(regex, '')
                        .replace('index.md', '__init__.py')
                        .replace('.md', '.py');
                    // 若文件名（不含扩展）和上级文件夹相同，返回文件夹/__init__.py
                    if (filePath.split('/').pop().split('.')[0] === filePath.split('/').slice(-2, -1)[0]) {
                        filePath = filePath.split('/').slice(0, -1).join('/') + '/__init__.py';
                    }
                    return `https://github.com/LiteyukiStudio/LiteyukiBot/tree/main/liteyuki${filePath}`;
                } else {
                    return `https://github.com/LiteyukiStudio/LiteyukiBot/tree/main/docs/${filePath}`;
                }
            },
            text: editPageText
        };
    },

    getOutLine: (label: string): { label: string; level: [number, number]; } => {
        return {
            label: label,
            level: [2, 6]
        };
    },

    copyright: 'Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved'
}
