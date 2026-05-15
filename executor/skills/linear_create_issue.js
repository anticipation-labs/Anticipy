// Linear — create an issue via GraphQL API. Reversible (archive in
// compensate). Picked over HubSpot per master prompt's "Linear or
// HubSpot" choice — Linear's API is cleaner and the test surface is
// smaller.

const axios = require('axios');
const { registry, VERIFIED, NOT_VERIFIED } = require('../lib/verifier');

const SKILL_ID = 'linear_create_issue';

const LINEAR_API = 'https://api.linear.app/graphql';

function buildRecipe(params) {
  return [
    {
      action: 'evaluate',
      target_ref: '__linear_create_issue__',
      value: JSON.stringify({
        teamId: params.teamId,
        title: params.title,
        description: params.description || '',
        priority: params.priority || 0,
      }),
      timeout_ms: 10000,
    },
  ];
}

async function callCreate(token, params) {
  const query = `mutation IssueCreate($input: IssueCreateInput!) {
    issueCreate(input: $input) {
      success
      issue { id identifier title url state { name } }
    }
  }`;
  const r = await axios.post(
    LINEAR_API,
    {
      query,
      variables: { input: { teamId: params.teamId, title: params.title, description: params.description, priority: params.priority } },
    },
    { headers: { Authorization: token, 'Content-Type': 'application/json' }, timeout: 10000 }
  );
  if (r.data.errors) throw new Error(JSON.stringify(r.data.errors));
  return r.data.data.issueCreate;
}

async function callArchive(token, issueId) {
  const query = `mutation IssueArchive($id: String!) {
    issueArchive(id: $id) { success }
  }`;
  const r = await axios.post(
    LINEAR_API,
    { query, variables: { id: issueId } },
    { headers: { Authorization: token, 'Content-Type': 'application/json' }, timeout: 10000 }
  );
  if (r.data.errors) throw new Error(JSON.stringify(r.data.errors));
  return r.data.data.issueArchive;
}

function verify(world) {
  const created = world?.result?.evidence?.parsed_confirmations?.[0];
  if (!created || !created.success) return { verdict: NOT_VERIFIED, reason: 'create_failed' };
  if (!created.issue?.id || !created.issue?.identifier) {
    return { verdict: NOT_VERIFIED, reason: 'no_issue_id_or_identifier' };
  }
  if (!created.issue?.url) return { verdict: NOT_VERIFIED, reason: 'no_issue_url' };
  return { verdict: VERIFIED, reason: 'issue_created', identifier: created.issue.identifier };
}

async function compensate(world) {
  const created = world?.result?.evidence?.parsed_confirmations?.[0];
  if (!created?.issue?.id) return true;
  const token = world?.token;
  if (!token) return false;
  await callArchive(token, created.issue.id);
  return true;
}

registry.register(SKILL_ID, verify, compensate);
module.exports = { SKILL_ID, buildRecipe, verify, compensate, callCreate, callArchive };
