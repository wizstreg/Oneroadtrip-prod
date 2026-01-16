#!/usr/bin/env node
/**
 * OneRoadTrip - Audit de structure projet
 * Usage: node audit-structure.js [chemin-racine]
 * Par défaut scanne le dossier courant
 */

const fs = require('fs');
const path = require('path');

// Configuration
const ROOT = process.argv[2] || '.';
const CONFIG_FILES = [
    '_redirects', '_headers', 'netlify.toml', 'firebase.json', 
    '.firebaserc', 'robots.txt', 'sitemap.xml', 'sitemap-index.xml',
    '.htaccess', '_htaccess', '.gitignore', '_gitignore',
    'package.json', 'node_modules'
];

const IGNORE_DIRS = ['node_modules', '.git', '.netlify', '.firebase', 'cache'];

// Résultats
const report = {
    root: path.resolve(ROOT),
    scanDate: new Date().toISOString(),
    structure: {},
    configFiles: [],
    warnings: [],
    stats: {
        totalFiles: 0,
        totalDirs: 0,
        byExtension: {},
        byFolder: {}
    },
    netlify: {
        redirects: [],
        headers: [],
        functions: []
    },
    seo: {
        sitemaps: [],
        robots: [],
        staticPages: { total: 0, byLang: {} }
    }
};

// Utilitaires
function getExtension(file) {
    const ext = path.extname(file).toLowerCase();
    return ext || '(no ext)';
}

function isIgnored(name) {
    return IGNORE_DIRS.includes(name) || name.startsWith('.');
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// Scanner récursif
function scanDirectory(dir, depth = 0, relativePath = '') {
    let result = {
        type: 'directory',
        files: 0,
        subdirs: 0,
        children: {},
        htmlFiles: [],
        configFiles: []
    };

    try {
        const entries = fs.readdirSync(dir, { withFileTypes: true });
        
        for (const entry of entries) {
            const fullPath = path.join(dir, entry.name);
            const relPath = path.join(relativePath, entry.name);

            if (entry.isDirectory()) {
                if (isIgnored(entry.name)) {
                    result.children[entry.name] = { type: 'ignored', reason: 'blacklist' };
                    continue;
                }

                result.subdirs++;
                report.stats.totalDirs++;

                // Scanner en profondeur mais limiter l'affichage
                if (depth < 4) {
                    result.children[entry.name] = scanDirectory(fullPath, depth + 1, relPath);
                } else {
                    // Compter seulement
                    const count = countFiles(fullPath);
                    result.children[entry.name] = { 
                        type: 'directory', 
                        files: count.files, 
                        subdirs: count.dirs,
                        note: '(détail non affiché - profondeur max)'
                    };
                }

                // Stats par dossier de premier niveau
                if (depth === 0) {
                    const folderStats = countFiles(fullPath);
                    report.stats.byFolder[entry.name] = folderStats;
                }

                // Détecter les fonctions Netlify
                if (entry.name === 'functions' || entry.name === 'netlify-functions') {
                    const funcs = fs.readdirSync(fullPath).filter(f => f.endsWith('.js') || f.endsWith('.ts'));
                    report.netlify.functions = funcs.map(f => ({ name: f, path: relPath }));
                }

            } else if (entry.isFile()) {
                result.files++;
                report.stats.totalFiles++;

                const ext = getExtension(entry.name);
                report.stats.byExtension[ext] = (report.stats.byExtension[ext] || 0) + 1;

                // Fichiers de config importants
                if (CONFIG_FILES.includes(entry.name)) {
                    const stat = fs.statSync(fullPath);
                    const configInfo = {
                        name: entry.name,
                        path: relPath,
                        size: formatSize(stat.size)
                    };
                    result.configFiles.push(configInfo);
                    report.configFiles.push(configInfo);

                    // Analyser les fichiers spécifiques
                    analyzeConfigFile(fullPath, entry.name, relPath);
                }

                // Compter les pages statiques par langue
                if (ext === '.html' && relativePath.includes('static-pages')) {
                    report.seo.staticPages.total++;
                    const langMatch = relPath.match(/static-pages[\/\\](\w{2})[\/\\]/);
                    if (langMatch) {
                        const lang = langMatch[1];
                        report.seo.staticPages.byLang[lang] = (report.seo.staticPages.byLang[lang] || 0) + 1;
                    }
                }
            }
        }
    } catch (err) {
        result.error = err.message;
    }

    return result;
}

// Compter les fichiers récursivement (sans détails)
function countFiles(dir) {
    let files = 0, dirs = 0;
    try {
        const entries = fs.readdirSync(dir, { withFileTypes: true });
        for (const entry of entries) {
            if (isIgnored(entry.name)) continue;
            if (entry.isDirectory()) {
                dirs++;
                const sub = countFiles(path.join(dir, entry.name));
                files += sub.files;
                dirs += sub.dirs;
            } else {
                files++;
            }
        }
    } catch (e) {}
    return { files, dirs };
}

// Analyser les fichiers de config spécifiques
function analyzeConfigFile(fullPath, name, relPath) {
    try {
        const content = fs.readFileSync(fullPath, 'utf8');

        if (name === '_redirects') {
            const lines = content.split('\n').filter(l => l.trim() && !l.startsWith('#'));
            const redirectInfo = {
                path: relPath,
                totalRules: lines.length,
                samples: lines.slice(0, 3),
                hasSPARule: lines.some(l => l.includes('/* ') && l.includes('200')),
                has301: lines.filter(l => l.includes('301')).length,
                has302: lines.filter(l => l.includes('302')).length
            };
            report.netlify.redirects.push(redirectInfo);

            // Warning si SPA rule au mauvais endroit
            if (redirectInfo.hasSPARule && relPath.includes('static-pages')) {
                report.warnings.push({
                    type: 'CRITICAL',
                    file: relPath,
                    message: 'Règle SPA (/* → /index.html 200) dans static-pages va bloquer les pages statiques!'
                });
            }
        }

        if (name === '_headers') {
            const blocks = content.split('\n\n').filter(b => b.trim());
            report.netlify.headers.push({
                path: relPath,
                totalBlocks: blocks.length,
                preview: content.substring(0, 500)
            });
        }

        if (name === 'robots.txt') {
            report.seo.robots.push({
                path: relPath,
                content: content,
                hasSitemap: content.includes('Sitemap:'),
                sitemapUrls: content.match(/Sitemap:\s*(\S+)/gi) || []
            });

            // Vérifier syntaxe
            if (content.includes('$')) {
                report.warnings.push({
                    type: 'WARNING',
                    file: relPath,
                    message: 'Utilisation de $ dans robots.txt - syntaxe Google uniquement, ignorée par autres bots'
                });
            }
        }

        if (name.includes('sitemap') && name.endsWith('.xml')) {
            const urlCount = (content.match(/<loc>/g) || []).length;
            report.seo.sitemaps.push({
                path: relPath,
                urlCount: urlCount,
                isIndex: content.includes('<sitemapindex'),
                size: formatSize(content.length)
            });

            // Warning si sitemap trop gros
            if (urlCount > 50000) {
                report.warnings.push({
                    type: 'ERROR',
                    file: relPath,
                    message: `Sitemap contient ${urlCount} URLs - limite Google = 50,000`
                });
            }
        }

        if (name === 'netlify.toml') {
            report.netlify.toml = {
                path: relPath,
                content: content.substring(0, 1000),
                hasRedirects: content.includes('[redirect'),
                hasHeaders: content.includes('[headers'),
                hasFunctions: content.includes('[functions')
            };
        }

    } catch (e) {
        report.warnings.push({
            type: 'ERROR',
            file: relPath,
            message: `Impossible de lire: ${e.message}`
        });
    }
}

// Détecter les conflits potentiels
function detectConflicts() {
    // Multiple _redirects
    if (report.netlify.redirects.length > 1) {
        report.warnings.push({
            type: 'WARNING',
            message: `${report.netlify.redirects.length} fichiers _redirects trouvés - Netlify n'utilise que celui à la racine!`,
            files: report.netlify.redirects.map(r => r.path)
        });
    }

    // Multiple robots.txt
    if (report.seo.robots.length > 1) {
        report.warnings.push({
            type: 'WARNING',
            message: `${report.seo.robots.length} fichiers robots.txt trouvés - seul celui à la racine compte!`,
            files: report.seo.robots.map(r => r.path)
        });
    }

    // SPA rule qui bloque static-pages
    const rootRedirects = report.netlify.redirects.find(r => !r.path.includes('/'));
    if (rootRedirects && rootRedirects.hasSPARule) {
        report.warnings.push({
            type: 'CRITICAL',
            message: 'La règle SPA "/* /index.html 200" à la racine va BLOQUER toutes les static-pages!',
            solution: 'Ajouter les exceptions AVANT la règle SPA dans _redirects'
        });
    }
}

// Générer le rapport texte
function generateTextReport() {
    let txt = '';
    txt += '═'.repeat(70) + '\n';
    txt += '  AUDIT STRUCTURE - ONEROADTRIP\n';
    txt += '═'.repeat(70) + '\n';
    txt += `Racine: ${report.root}\n`;
    txt += `Date: ${report.scanDate}\n\n`;

    // Stats globales
    txt += '─'.repeat(70) + '\n';
    txt += '📊 STATISTIQUES GLOBALES\n';
    txt += '─'.repeat(70) + '\n';
    txt += `Total fichiers: ${report.stats.totalFiles}\n`;
    txt += `Total dossiers: ${report.stats.totalDirs}\n\n`;

    txt += 'Par extension:\n';
    const sortedExt = Object.entries(report.stats.byExtension).sort((a, b) => b[1] - a[1]);
    for (const [ext, count] of sortedExt.slice(0, 15)) {
        txt += `  ${ext.padEnd(12)} ${count}\n`;
    }

    txt += '\nPar dossier (1er niveau):\n';
    for (const [folder, stats] of Object.entries(report.stats.byFolder)) {
        txt += `  ${folder.padEnd(25)} ${stats.files} fichiers, ${stats.dirs} dossiers\n`;
    }

    // Pages statiques SEO
    txt += '\n' + '─'.repeat(70) + '\n';
    txt += '🌐 PAGES STATIQUES SEO\n';
    txt += '─'.repeat(70) + '\n';
    txt += `Total: ${report.seo.staticPages.total} pages\n`;
    txt += 'Par langue:\n';
    for (const [lang, count] of Object.entries(report.seo.staticPages.byLang)) {
        txt += `  ${lang.toUpperCase()}: ${count}\n`;
    }

    // Config Netlify
    txt += '\n' + '─'.repeat(70) + '\n';
    txt += '⚙️  CONFIGURATION NETLIFY\n';
    txt += '─'.repeat(70) + '\n';

    txt += '\n_redirects trouvés:\n';
    for (const r of report.netlify.redirects) {
        txt += `  📄 ${r.path}\n`;
        txt += `     - ${r.totalRules} règles (${r.has301} x 301, ${r.has302} x 302)\n`;
        txt += `     - Règle SPA: ${r.hasSPARule ? '⚠️  OUI' : 'Non'}\n`;
    }

    txt += '\n_headers trouvés:\n';
    for (const h of report.netlify.headers) {
        txt += `  📄 ${h.path} (${h.totalBlocks} blocs)\n`;
    }

    if (report.netlify.functions.length > 0) {
        txt += '\nFonctions Netlify:\n';
        for (const f of report.netlify.functions) {
            txt += `  ⚡ ${f.name}\n`;
        }
    }

    // SEO
    txt += '\n' + '─'.repeat(70) + '\n';
    txt += '🔍 FICHIERS SEO\n';
    txt += '─'.repeat(70) + '\n';

    txt += '\nSitemaps:\n';
    for (const s of report.seo.sitemaps) {
        txt += `  📄 ${s.path}\n`;
        txt += `     - ${s.urlCount} URLs, ${s.size}\n`;
        txt += `     - Type: ${s.isIndex ? 'Index' : 'Sitemap'}\n`;
    }

    txt += '\nrobots.txt:\n';
    for (const r of report.seo.robots) {
        txt += `  📄 ${r.path}\n`;
        txt += `     - Sitemaps déclarés: ${r.sitemapUrls.length}\n`;
    }

    // Tous les fichiers de config
    txt += '\n' + '─'.repeat(70) + '\n';
    txt += '📋 TOUS LES FICHIERS DE CONFIG TROUVÉS\n';
    txt += '─'.repeat(70) + '\n';
    for (const c of report.configFiles) {
        txt += `  ${c.path.padEnd(50)} ${c.size}\n`;
    }

    // WARNINGS
    if (report.warnings.length > 0) {
        txt += '\n' + '═'.repeat(70) + '\n';
        txt += '⚠️  PROBLÈMES DÉTECTÉS\n';
        txt += '═'.repeat(70) + '\n';
        for (const w of report.warnings) {
            const icon = w.type === 'CRITICAL' ? '🔴' : w.type === 'ERROR' ? '🟠' : '🟡';
            txt += `\n${icon} [${w.type}] ${w.message}\n`;
            if (w.file) txt += `   Fichier: ${w.file}\n`;
            if (w.files) txt += `   Fichiers: ${w.files.join(', ')}\n`;
            if (w.solution) txt += `   💡 Solution: ${w.solution}\n`;
        }
    }

    txt += '\n' + '═'.repeat(70) + '\n';
    txt += '  FIN DU RAPPORT\n';
    txt += '═'.repeat(70) + '\n';

    return txt;
}

// Main
console.log('🔍 Scan en cours de:', path.resolve(ROOT));
console.log('   (peut prendre quelques secondes...)\n');

report.structure = scanDirectory(ROOT);
detectConflicts();

// Sauvegarder les rapports
const textReport = generateTextReport();
const jsonReport = JSON.stringify(report, null, 2);

fs.writeFileSync('audit-report.txt', textReport);
fs.writeFileSync('audit-report.json', jsonReport);

console.log(textReport);
console.log('\n✅ Rapports générés:');
console.log('   - audit-report.txt (lisible)');
console.log('   - audit-report.json (détaillé)');
