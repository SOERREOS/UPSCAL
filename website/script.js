const root = document.documentElement;
const floatItems = document.querySelectorAll(".float");
const compareBlocks = document.querySelectorAll("[data-compare]");
const featureCopy = document.querySelector("#feature-copy");
const featureControls = document.querySelectorAll("[data-panel]");
const magneticItems = document.querySelectorAll(".magnetic");
const downloadLinks = document.querySelectorAll("[data-direct-download]");

const copy = {
  local:
    "이미지는 내 PC에서 처리되고, GPU가 감지되면 CUDA 가속을 활용합니다. 민감한 원본을 외부로 보내지 않고도 더 큰 결과를 만들 수 있습니다.",
  queue:
    "여러 이미지를 작업 큐에 올려두고 순서대로 처리합니다. 완료된 항목은 저장 흐름으로 이어져 반복 작업을 줄여줍니다.",
  detail:
    "Real-ESRGAN 결과에 디테일 복원 단계를 더해 가장자리, 곡선, 질감이 더 또렷하게 보이도록 다듬습니다.",
  output:
    "사진/그림 모델, 배율, DPI, 포맷, 타일 크기, 디테일 강도를 한 화면에서 조절하고 바로 저장합니다.",
};

let targetX = 0;
let targetY = 0;
let currentX = 0;
let currentY = 0;
function updatePointer(event) {
  targetX = (event.clientX / window.innerWidth - 0.5) * 2;
  targetY = (event.clientY / window.innerHeight - 0.5) * 2;
}

function animate() {
  currentX += (targetX - currentX) * 0.075;
  currentY += (targetY - currentY) * 0.075;

  root.style.setProperty("--tilt-x", `${(-currentY * 4.2).toFixed(2)}deg`);
  root.style.setProperty("--tilt-y", `${(currentX * 5.2).toFixed(2)}deg`);

  floatItems.forEach((item) => {
    const depth = Number(item.dataset.depth || 0);
    item.style.setProperty("--tx", `${(currentX * depth).toFixed(2)}px`);
    item.style.setProperty("--ty", `${(currentY * depth).toFixed(2)}px`);
  });

  requestAnimationFrame(animate);
}

window.addEventListener("pointermove", updatePointer, { passive: true });
window.addEventListener("pointerleave", () => {
  targetX *= 0.35;
  targetY *= 0.35;
});
animate();

function setSplit(block, clientX) {
  const rect = block.getBoundingClientRect();
  const raw = ((clientX - rect.left) / rect.width) * 100;
  const next = Math.min(88, Math.max(12, raw));
  block.style.setProperty("--split", `${next}%`);
  block.setAttribute("aria-valuenow", Math.round(next));
}

compareBlocks.forEach((block) => {
  let dragging = false;

  block.addEventListener("pointerdown", (event) => {
    dragging = true;
    block.setPointerCapture(event.pointerId);
    setSplit(block, event.clientX);
  });

  block.addEventListener("pointermove", (event) => {
    if (dragging) {
      setSplit(block, event.clientX);
    }
  });

  block.addEventListener("pointerup", () => {
    dragging = false;
  });

  block.addEventListener("pointercancel", () => {
    dragging = false;
  });

  block.addEventListener("keydown", (event) => {
    const current = Number(block.getAttribute("aria-valuenow")) || 52;
    const step = event.shiftKey ? 10 : 4;
    let next = current;

    if (event.key === "ArrowLeft") next = current - step;
    if (event.key === "ArrowRight") next = current + step;

    if (next !== current) {
      event.preventDefault();
      next = Math.min(88, Math.max(12, next));
      block.style.setProperty("--split", `${next}%`);
      block.setAttribute("aria-valuenow", next);
    }
  });
});

function setMode(mode) {
  root.dataset.mode = mode;
  if (featureCopy && copy[mode]) {
    featureCopy.textContent = copy[mode];
  }

  featureControls.forEach((control) => {
    control.classList.toggle("is-active", control.dataset.panel === mode && control.classList.contains("feature-chip"));
  });
}

featureControls.forEach((control) => {
  control.addEventListener("click", () => {
    const mode = control.dataset.panel;
    if (mode) setMode(mode);
  });
});

magneticItems.forEach((item) => {
  item.addEventListener("pointermove", (event) => {
    const rect = item.getBoundingClientRect();
    const x = event.clientX - (rect.left + rect.width / 2);
    const y = event.clientY - (rect.top + rect.height / 2);
    item.style.setProperty("--mx", `${x * 0.13}px`);
    item.style.setProperty("--my", `${y * 0.13}px`);
  });

  item.addEventListener("pointerleave", () => {
    item.style.setProperty("--mx", "0px");
    item.style.setProperty("--my", "0px");
  });
});

function startDownload(url, filename) {
  const resolved = new URL(url, window.location.href);
  const anchor = document.createElement("a");
  anchor.href = resolved.href;
  anchor.download = filename || "";
  anchor.rel = "noopener";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

downloadLinks.forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    link.setAttribute("aria-busy", "true");
    startDownload(link.href, link.dataset.filename || link.getAttribute("download"));

    setTimeout(() => {
      link.removeAttribute("aria-busy");
    }, 1500);
  });
});

setMode("local");
