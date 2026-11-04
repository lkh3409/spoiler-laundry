const API = "http://127.0.0.1:8765/api";

// 유튜브 페이지가 직접 부를 수 없는 로컬 서버 요청을 대신 처리한다
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const { path, body } = message;
  const options = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {};
  fetch(`${API}${path}`, options)
    .then(async (response) => sendResponse({ ok: response.ok, status: response.status, data: response.ok ? await response.json() : null }))
    .catch((error) => {
      console.error("[스포 세탁소] 서버 요청 실패", path, error);
      sendResponse({ ok: false, status: 0, data: null });
    });
  return true;
});
