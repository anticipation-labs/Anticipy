// Skill registry — every skill module self-registers with the
// verifier registry on require. Importing this module loads all
// available skills.

const fs = require('fs');
const path = require('path');

const { registry } = require('../lib/verifier');

const SKILLS_DIR = __dirname;

function loadAll() {
  const files = fs.readdirSync(SKILLS_DIR).filter((f) =>
    f.endsWith('.js') && f !== 'index.js'
  );
  const loaded = [];
  for (const f of files) {
    const mod = require(path.join(SKILLS_DIR, f));
    if (mod && mod.SKILL_ID) loaded.push(mod.SKILL_ID);
  }
  return loaded;
}

// Eagerly load on module require.
const loadedIds = loadAll();
console.log(`[skills] loaded ${loadedIds.length} skill(s): ${loadedIds.join(', ')}`);

module.exports = { registry, loadedIds, loadAll };
