import './style.css'

interface Comment {
  user: string;
  content: string;
  time: string;
  location: string;
  image_path?: string | null;
  scrape_time: string;
  replies?: Comment[];
}

interface ManifestEntry {
  id: string;
  url: string;
  title: string;
  scrape_date: string;
  comment_count: number;
}

interface AppState {
  manifest: ManifestEntry[];
  selectedId: string | null;
  comments: Comment[];
  counts: Record<string, number>;
  votedIndices: string[]; // Use user+time+content as key for persistence across reloads
}

const state: AppState = {
  manifest: [],
  selectedId: null,
  comments: [],
  counts: JSON.parse(localStorage.getItem('douyin_location_counts') || '{}'),
  votedIndices: JSON.parse(localStorage.getItem('douyin_voted_indices') || '[]')
};

async function init() {
  await loadManifest();
}

async function loadManifest() {
  const noteListEl = document.getElementById('note-list');
  try {
    const response = await fetch('/scraped_data/manifest.json');
    state.manifest = await response.json();
    renderNoteList();
    
    // Auto-select first one if available
    if (state.manifest.length > 0) {
      selectNote(state.manifest[0].id);
    }
  } catch (err) {
    if (noteListEl) noteListEl.innerHTML = `<div class="error">无法加载任务列表</div>`;
    console.error(err);
  }
}

async function selectNote(id: string) {
  state.selectedId = id;
  renderNoteList();
  
  const feedEl = document.getElementById('comment-feed');
  if (feedEl) feedEl.innerHTML = `<div class="loading">正在加载 ${id} 的数据...</div>`;
  
  try {
    const response = await fetch(`/scraped_data/${id}/comments.json`);
    state.comments = await response.json();
    renderContent();
  } catch (err) {
    if (feedEl) feedEl.innerHTML = `<div class="error">无法加载数据 [${id}]</div>`;
    console.error(err);
  }
}

function renderNoteList() {
  const noteListEl = document.getElementById('note-list');
  if (!noteListEl) return;
  
  noteListEl.innerHTML = state.manifest.map(entry => `
    <div class="note-item ${state.selectedId === entry.id ? 'active' : ''}" onclick="window.selectNote('${entry.id}')">
      <span class="note-id" title="ID: ${entry.id}">${entry.title || entry.id}</span>
      <div class="note-meta">
        <span>${entry.comment_count} 评论</span>
        <span>${entry.scrape_date.split(' ')[0]}</span>
      </div>
    </div>
  `).join('');
}

function getCommentUid(comment: Comment) {
  return `${comment.user}_${comment.time}_${comment.content.substring(0, 20)}`;
}

function toggleVote(comment: Comment) {
  const location = comment.location;
  if (!location || location === 'Unknown' || location === '未知') return;

  const uid = getCommentUid(comment);
  const votePos = state.votedIndices.indexOf(uid);
  
  if (votePos > -1) {
    state.votedIndices.splice(votePos, 1);
    state.counts[location] = Math.max(0, (state.counts[location] || 0) - 1);
  } else {
    state.votedIndices.push(uid);
    state.counts[location] = (state.counts[location] || 0) + 1;
  }

  saveState();
  renderContent(); 
}

function clearStats() {
  if (confirm('确定要清空所有统计数据吗？')) {
    state.counts = {};
    state.votedIndices = [];
    saveState();
    renderContent();
  }
}

function saveState() {
  localStorage.setItem('douyin_location_counts', JSON.stringify(state.counts));
  localStorage.setItem('douyin_voted_indices', JSON.stringify(state.votedIndices));
}

function renderStats() {
  const statListEl = document.getElementById('stat-list');
  if (!statListEl) return;

  const sortedStats = Object.entries(state.counts)
    .filter(([_, count]) => count > 0)
    .sort((a, b) => b[1] - a[1]);

  if (sortedStats.length === 0) {
    statListEl.innerHTML = `<p style="color: var(--text-dim); font-size: 0.9rem;">还没有点击记录...</p>`;
    return;
  }

  statListEl.innerHTML = sortedStats.map(([loc, count]) => `
    <div class="stat-item">
      <span class="stat-loc">${loc}</span>
      <span class="stat-count">${count}</span>
    </div>
  `).join('');
}

function renderComment(comment: Comment, isReply = false): string {
  const uid = getCommentUid(comment);
  const isVoted = state.votedIndices.includes(uid);
  const hasImage = !!comment.image_path;
  const imageUrl = hasImage ? `/scraped_data/${state.selectedId}/${comment.image_path}` : '';
  
  const repliesHtml = (comment.replies && comment.replies.length > 0) 
    ? `<div class="replies-container">
        ${comment.replies.map(r => renderComment(r, true)).join('')}
       </div>`
    : '';

  return `
    <div class="comment-card ${isReply ? 'reply-card' : ''} ${isVoted ? 'voted' : ''}">
      <div class="card-header">
        <div class="user-info">
          <span class="user-name">${comment.user || '匿名用户'}</span>
          <div class="meta">
            <span>${comment.time}</span>
            <span>•</span>
            <span>${comment.location || '未知'}</span>
          </div>
        </div>
      </div>
      
      <div class="content">
        ${comment.content || '[无内容]'}
      </div>

      ${hasImage ? `
        <div class="comment-image-container">
          <img class="comment-image" src="${imageUrl}" loading="lazy" alt="Comment attachment" />
        </div>
      ` : ''}

      <div class="card-footer">
        <button class="vote-btn ${isVoted ? 'active' : ''}" onclick="window.handleVote('${uid}')">
          <span>${isVoted ? '✅' : '✨'}</span> ${isVoted ? '已计入' : '汇总计数'}
        </button>
      </div>

      ${repliesHtml}
    </div>
  `;
}

function renderContent() {
  const feedEl = document.getElementById('comment-feed');
  if (!feedEl) return;

  if (state.comments.length === 0) {
    feedEl.innerHTML = `<div class="loading">该任务暂无评论数据</div>`;
  } else {
    feedEl.innerHTML = state.comments.map(c => renderComment(c)).join('');
  }

  renderStats();
}

// Expose handlers to window
(window as any).selectNote = (id: string) => {
  selectNote(id);
};
(window as any).handleVote = (uid: string) => {
  // Find the comment by UID to get its location
  const allComments = flattenComments(state.comments);
  const comment = allComments.find(c => getCommentUid(c) === uid);
  if (comment) toggleVote(comment);
};
(window as any).clearStats = () => {
  clearStats();
};

function flattenComments(comments: Comment[]): Comment[] {
  let result: Comment[] = [];
  for (const c of comments) {
    result.push(c);
    if (c.replies) {
      result = result.concat(flattenComments(c.replies));
    }
  }
  return result;
}

init();
