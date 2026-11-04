(() => {
  const COMMENT_SELECTOR = "ytd-comment-view-model #content-text, ytd-comment-renderer #content-text";
  // pipeline.py의 FALLBACK_WASH와 같은 문구. 이 답을 받으면 맡김표로 보여 준다
  const FALLBACK_WASH = "(스포일러가 포함된 댓글이에요. 관람 후 공개)";
  const MAX_STAINS = 8;
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
    panelParts: null,
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
    Object.assign(state, { videoId: null, movieId: null, segments: [], watched: false, washed: new Map(), pending: new Set(), skipped: 0, observer: null, video: null, panel: null, panelParts: null, timer: null, markerDuration: null });
  }

  async function start() {
    reset();
    const videoId = currentVideoId();
    if (!videoId) return;
    console.log("[스포 세탁소] 시작", videoId);
    showStatus("세탁소 문 여는 중…");
    const response = await api(`/videos/${videoId}`).catch((error) => {
      console.error("[스포 세탁소] 메시지 실패", error);
      return null;
    });
    console.log("[스포 세탁소] 서버 응답", response);
    if (currentVideoId() !== videoId) return;
    // 등록하지 않은 영상에서는 화면에 아무것도 남기지 않는다
    if (response?.status === 404) {
      reset();
      return;
    }
    if (!response?.ok) {
      showStatus(`오늘은 문을 닫았어요 (서버 상태 ${response?.status ?? "응답 없음"})`);
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
    toast(`${Math.round(segment.end - segment.start)}초짜리 얼룩을 지웠어요`);
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
    state.pending.add(element);
    renderPanel();
    const cached = state.washed.get(key);
    const result = cached ?? (await api(`/videos/${state.videoId}/comments`, { text: key }));
    element.classList.remove("sl-checking");
    state.pending.delete(element);
    if (!result?.ok) {
      element.classList.add("sl-unchecked");
      element.title = "세탁소 문이 닫혀 있어 확인하지 못했어요";
      renderPanel();
      return;
    }
    state.washed.set(key, result);
    if (result.data.spoiler && !state.watched) showWashed(element, result.data.washed, key);
    renderPanel();
  }

  function showWashed(element, washed, key) {
    const isTicket = washed === FALLBACK_WASH;
    element.textContent = isTicket ? `맡김표 No.${ticketNumber(key)} · 스포 얼룩이 심해 보관 중이에요. 영화를 보고 찾아가세요` : washed;
    element.classList.add("sl-washed", isTicket ? "sl-ticket" : "sl-clean");
    element.title = "스포 세탁소에서 세탁한 댓글이에요";
  }

  function ticketNumber(text) {
    let hash = 0;
    for (const char of text) hash = (hash * 31 + char.codePointAt(0)) % 900;
    return hash + 100;
  }

  function restoreAll() {
    document.querySelectorAll("[data-sl-original]").forEach((element) => {
      if (element.classList.contains("sl-washed")) element.textContent = element.dataset.slOriginal;
      element.classList.remove("sl-washed", "sl-clean", "sl-ticket", "sl-checking", "sl-unchecked");
      element.removeAttribute("title");
    });
  }

  async function setWatched(watched) {
    const count = document.querySelectorAll(".sl-washed").length;
    state.watched = watched;
    await chrome.storage.local.set({ [watchedKey()]: watched });
    if (watched) {
      restoreAll();
      toast(`맡기신 댓글 ${count}장, 얼룩 구간 ${state.segments.length}곳을 돌려드렸어요`);
    } else {
      document.querySelectorAll("[data-sl-original]").forEach((element) => washComment(element, element.dataset.slOriginal));
    }
    drawMarkers();
    renderPanel();
  }

  function appendElement(parent, tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text) element.textContent = text;
    parent.appendChild(element);
    return element;
  }

  // 드럼 회전이 끊기지 않도록 패널은 한 번만 만들고 내용만 바꾼다
  function ensurePanel() {
    if (state.panel) return;
    const panel = appendElement(document.body, "div", "sl-panel");
    const washer = appendElement(panel, "div", "sl-washer");
    const top = appendElement(washer, "div", "sl-washer-top");
    appendElement(top, "i");
    appendElement(top, "i");
    const door = appendElement(washer, "div", "sl-door");
    const drum = appendElement(door, "div", "sl-drum");
    appendElement(drum, "b", "sl-paddle");
    const info = appendElement(panel, "div", "sl-info");
    appendElement(info, "strong", "", "스포 세탁소");
    const status = appendElement(info, "span", "sl-status");
    const button = appendElement(info, "button", "sl-button");
    button.addEventListener("click", () => setWatched(!state.watched));
    state.panel = panel;
    state.panelParts = { drum, status, button };
  }

  function showStatus(message) {
    ensurePanel();
    state.panelParts.status.textContent = message;
    state.panelParts.button.hidden = true;
  }

  function renderPanel() {
    ensurePanel();
    const { drum, status, button } = state.panelParts;
    const washedCount = document.querySelectorAll(".sl-washed").length;
    const pendingCount = state.pending.size;
    state.panel.classList.toggle("is-washing", pendingCount > 0);
    if (state.watched) status.textContent = "세탁물을 모두 찾아가셨어요";
    else if (pendingCount > 0) status.textContent = `세탁 중… 남은 댓글 ${pendingCount}장`;
    else status.textContent = `오늘 세탁물: 얼룩 구간 ${state.segments.length}곳, 댓글 ${washedCount}장`;
    button.hidden = false;
    button.textContent = state.watched ? "다시 맡기기" : "세탁물 찾아가기";

    // 세탁한 댓글 수만큼 드럼 안에 얼룩을 쌓는다
    const wanted = state.watched ? 0 : Math.min(washedCount, MAX_STAINS);
    drum.querySelectorAll(".sl-stain").forEach((stain) => stain.remove());
    for (let i = 0; i < wanted; i += 1) {
      appendElement(drum, "i", `sl-stain sl-stain-${i}`);
    }
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
