import './style.css'

interface Comment {
  user: string;
  content: string;
  time: string;
  location: string;
  image_path?: string | null;
  scrape_time: string;
}

interface AppState {
  comments: Comment[];
  counts: Record<string, number>;
  votedIndices: number[];
}

const state: AppState = {
  comments: [],
  counts: JSON.parse(localStorage.getItem('douyin_location_counts') || '{}'),
  votedIndices: JSON.parse(localStorage.getItem('douyin_voted_indices') || '[]')
};

async function init() {
  const feedEl = document.getElementById('comment-feed');

  try {
    const response = await fetch('/comments.json');
    state.comments = await response.json();
    renderContent();
  } catch (err) {
    if (feedEl) feedEl.innerHTML = `<div class="error">无法加载数据，请确保 comments.json 存在于 public 目录。</div>`;
    console.error(err);
  }
}

function toggleVote(index: number, location: string) {
  if (!location || location === 'Unknown') return;

  const votePos = state.votedIndices.indexOf(index);
  if (votePos > -1) {
    // Already voted, so remove it
    state.votedIndices.splice(votePos, 1);
    state.counts[location] = Math.max(0, (state.counts[location] || 0) - 1);
  } else {
    // New vote
    state.votedIndices.push(index);
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

function renderContent() {
  const feedEl = document.getElementById('comment-feed');
  if (!feedEl) return;

  feedEl.innerHTML = state.comments.map((comment, index) => {
    const hasImage = comment.image_path && comment.image_path !== null;
    const isVoted = state.votedIndices.includes(index);
    
    return `
      <div class="comment-card ${isVoted ? 'voted' : ''}" data-index="${index}">
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
            <img class="comment-image" src="/${comment.image_path}" loading="lazy" alt="Comment attachment" />
          </div>
        ` : ''}

        <div class="card-footer">
          <button class="vote-btn ${isVoted ? 'active' : ''}" onclick="window.handleVote(${index}, '${comment.location}')">
            <span>${isVoted ? '✅' : '✨'}</span> ${isVoted ? '已计入' : '汇总计数'}
          </button>
        </div>
      </div>
    `;
  }).join('');

  renderStats();
}

// Expose handlers to window
(window as any).handleVote = (index: number, location: string) => {
  toggleVote(index, location);
};
(window as any).clearStats = () => {
  clearStats();
};

init();
