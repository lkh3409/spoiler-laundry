(() => {
  const COMMENT_SELECTOR = "ytd-comment-view-model #content-text, ytd-comment-renderer #content-text";
  const state = {
    videoId: null,
    movieId: null,
    segments: [],
    watched: false,
    washed: new Map(),
    pending: new Set(),
    skipped: 0,
    observer: null,
    video: null,
    panel: null,
    timer: null,
    markerDuration: null,
  };

  const api = (path, body) => new Promise((resolve) => chrome.runtime.sendMessage({ path, body }, resolve));
  const normalize = (text) => text.replace(/\s+/g, " ").trim();
  const watchedKey = () => `watched:${state.movieId}`;

  function currentVideoId() {
    return location.pathname === "/watch" ? new URLSearchParams(location.search).get("v") : null;
  }

  function reset() {
    state.observer?.disconnect();
    clearInterval(state.timer);
    state.panel?.remove();
    document.querySelectorAll(".sl-marker").forEach((marker) => marker.remove());
    Object.assign(state, { videoId: null, movieId: null, segments: [], watched: false, washed: new Map(), pending: new Set(), skipped: 0, observer: null, video: null, panel: null, timer: null, markerDuration: null });
  }

  async function start() {
    reset();
    const videoId = currentVideoId();
    if (!videoId) return;
    console.log("[스포 세탁소] 시작", videoId);
    showStatus("서버 확인 중…");
    const response = await api(`/videos/${videoId}`).catch((error) => {
      console.error("[스포 세탁소] 메시지 실패", error);
      return null;
    });
    console.log("[스포 세탁소] 서버 응답", response);
    if (currentVideoId() !== videoId) return;
    if (!response?.ok) {
      showStatus(response?.status === 404 ? "등록되지 않은 영상이에요" : `서버 연결 실패 (상태 ${response?.status ?? "응답 없음"})`);
      return;
    }

    state.videoId = videoId;
    state.movieId = response.data.movie_id;
    state.segments = response.data.segments;
    const stored = await chrome.storage.local.get(watchedKey());
    state.watched = Boolean(stored[watchedKey()]);

    renderPanel();
    attachVideo();
    drawMarkers();
    state.observer = new MutationObserver(scanComments);
    state.observer.observe(document.body, { childList: true, subtree: true });
    scanComments();
  }

  // 유튜브가 영상 요소를 늦게 만들거나 바꿀 수 있어 이벤트 대신 주기적으로 확인한다
  function attachVideo() {
    state.timer = setInterval(checkSkip, 250);
  }

  function checkSkip() {
    const video = document.querySelector("video.html5-main-video");
    if (video && video !== state.video) {
      state.video = video;
      console.log("[스포 세탁소] 영상 연결", video.duration);
    }
    // 광고 중에는 재생 위치와 길이가 광고 기준이라 구간 표시와 건너뛰기를 멈춘다
    if (!video || document.querySelector(".html5-video-player.ad-showing")) return;
    syncMarkers(video);
    if (state.watched) return;
    const now = video.currentTime;
    const segment = state.segments.find((s) => now >= s.start && now < s.end);
    if (!segment) return;
    console.log("[스포 세탁소] 건너뛰기", now, "->", segment.end);
    video.currentTime = segment.end;
    state.skipped += 1;
    toast(`스포 구간을 건너뛰었어요 (${Math.round(segment.end - segment.start)}초)`);
    renderPanel();
  }

  // 유튜브가 광고 전후로 진행 바를 다시 그리면 표시가 사라지므로 빠졌을 때마다 다시 넣는다
  function syncMarkers(video) {
    const wanted = state.watched ? 0 : state.segments.length;
    const stale = state.markerDuration !== video.duration;
    if (document.querySelectorAll(".ytp-progress-bar .sl-marker").length !== wanted || stale) drawMarkers();
  }

  function drawMarkers() {
    const bar = document.querySelector(".ytp-progress-bar");
    const duration = state.video?.duration;
    if (!bar || !duration || !Number.isFinite(duration)) return;
    document.querySelectorAll(".sl-marker").forEach((marker) => marker.remove());
    state.markerDuration = duration;
    if (state.watched) return;
    console.log("[스포 세탁소] 구간 표시", state.segments.length, duration);
    for (const segment of state.segments) {
      const marker = document.createElement("div");
      marker.className = "sl-marker";
      marker.style.left = `${(segment.start / duration) * 100}%`;
      marker.style.width = `${((segment.end - segment.start) / duration) * 100}%`;
      bar.appendChild(marker);
    }
  }

  function scanComments() {
    document.querySelectorAll(COMMENT_SELECTOR).forEach((element) => {
      if (element.dataset.slOriginal !== undefined) return;
      const original = element.textContent;
      element.dataset.slOriginal = original;
      if (state.watched) return;
      washComment(element, original);
    });
  }

  // 판단이 끝나기 전에 읽히지 않도록 먼저 흐리게 가린다
  async function washComment(element, original) {
    const key = normalize(original);
    element.classList.add("sl-checking");
    const cached = state.washed.get(key);
    const result = cached ?? (await api(`/videos/${state.videoId}/comments`, { text: key }));
    element.classList.remove("sl-checking");
    if (!result?.ok) {
      element.classList.add("sl-unchecked");
      element.title = "서버에 연결되지 않아 확인하지 못했어요";
      return;
    }
    state.washed.set(key, result);
    if (!result.data.spoiler || state.watched) return;
    element.textContent = result.data.washed;
    element.classList.add("sl-washed");
    element.title = "스포 세탁소가 세탁한 댓글이에요";
    renderPanel();
  }

  function restoreAll() {
    document.querySelectorAll("[data-sl-original]").forEach((element) => {
      if (element.classList.contains("sl-washed")) element.textContent = element.dataset.slOriginal;
      element.classList.remove("sl-washed", "sl-checking", "sl-unchecked");
      element.removeAttribute("title");
    });
  }

  async function setWatched(watched) {
    const count = document.querySelectorAll(".sl-washed").length;
    state.watched = watched;
    await chrome.storage.local.set({ [watchedKey()]: watched });
    if (watched) {
      restoreAll();
      toast(`해금 완료! 세탁한 댓글 ${count}개와 스포 구간 ${state.segments.length}개를 열었어요`);
    } else {
      document.querySelectorAll("[data-sl-original]").forEach((element) => washComment(element, element.dataset.slOriginal));
    }
    drawMarkers();
    renderPanel();
  }

  function showStatus(message) {
    if (!state.panel) {
      state.panel = document.createElement("div");
      state.panel.className = "sl-panel";
      document.body.appendChild(state.panel);
    }
    state.panel.textContent = `스포 세탁소: ${message}`;
  }

  function renderPanel() {
    if (!state.panel) {
      state.panel = document.createElement("div");
      state.panel.className = "sl-panel";
      document.body.appendChild(state.panel);
    }
    const washedCount = document.querySelectorAll(".sl-washed").length;
    state.panel.textContent = "";
    const title = document.createElement("strong");
    title.textContent = "스포 세탁소";
    const status = document.createElement("span");
    status.textContent = state.watched
      ? "관람 완료: 원본 표시 중"
      : `스포 구간 ${state.segments.length}개 · 세탁 댓글 ${washedCount}개`;
    const button = document.createElement("button");
    button.textContent = state.watched ? "다시 가리기" : "영화 봤어요";
    button.addEventListener("click", () => setWatched(!state.watched));
    state.panel.append(title, status, button);
  }

  function toast(message) {
    const element = document.createElement("div");
    element.className = "sl-toast";
    element.textContent = message;
    document.body.appendChild(element);
    setTimeout(() => element.remove(), 3000);
  }

  // 유튜브는 페이지를 새로 읽지 않고 영상을 바꾸므로 이동 이벤트마다 다시 시작한다
  window.addEventListener("yt-navigate-finish", start);
  start();
})();
