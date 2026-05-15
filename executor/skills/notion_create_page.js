// Notion create page — uses Notion API with integration token.

const axios = require('axios');
const { registry, VERIFIED, NOT_VERIFIED } = require('../lib/verifier');

const SKILL_ID = 'notion_create_page';

const NOTION_VERSION = '2022-06-28';

function buildRecipe(params) {
  return [
    {
      action: 'evaluate',
      target_ref: '__notion_create__',
      value: JSON.stringify({
        parent_database_id: params.parent_database_id,
        title: params.title,
        body: params.body || '',
      }),
      timeout_ms: 10000,
    },
  ];
}

async function callCreate(token, params) {
  const body = {
    parent: { database_id: params.parent_database_id },
    properties: {
      Name: { title: [{ text: { content: params.title } }] },
    },
    children: params.body
      ? [
          {
            object: 'block',
            type: 'paragraph',
            paragraph: { rich_text: [{ type: 'text', text: { content: params.body } }] },
          },
        ]
      : [],
  };
  const r = await axios.post(
    'https://api.notion.com/v1/pages',
    body,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        'Notion-Version': NOTION_VERSION,
        'Content-Type': 'application/json',
      },
      timeout: 10000,
    }
  );
  return r.data;
}

async function callArchive(token, pageId) {
  const r = await axios.patch(
    `https://api.notion.com/v1/pages/${encodeURIComponent(pageId)}`,
    { archived: true },
    {
      headers: {
        Authorization: `Bearer ${token}`,
        'Notion-Version': NOTION_VERSION,
        'Content-Type': 'application/json',
      },
      timeout: 10000,
    }
  );
  return r.data;
}

function verify(world) {
  const created = world?.result?.evidence?.parsed_confirmations?.[0];
  if (!created?.id) return { verdict: NOT_VERIFIED, reason: 'no_page_id' };
  if (created.object !== 'page') return { verdict: NOT_VERIFIED, reason: 'not_a_page' };
  if (!created.url) return { verdict: NOT_VERIFIED, reason: 'no_url' };
  return { verdict: VERIFIED, reason: 'page_created', pageId: created.id };
}

async function compensate(world) {
  const created = world?.result?.evidence?.parsed_confirmations?.[0];
  if (!created?.id) return true;
  const token = world?.token;
  if (!token) return false;
  await callArchive(token, created.id);
  return true;
}

registry.register(SKILL_ID, verify, compensate);
module.exports = { SKILL_ID, buildRecipe, verify, compensate, callCreate, callArchive };
