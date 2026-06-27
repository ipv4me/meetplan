/* MeetPlan — клиентская логика (FullCalendar + jQuery AJAX) */

let calendar = null;
let activeEvent = null; // событие, открытое в модалке деталей

document.addEventListener("DOMContentLoaded", function () {
  const el = document.getElementById("calendar");
  if (el) initCalendar(el);
  bindNewEventModal();
  startNotificationPolling();
  initThemeToggle();
  initTasks();
  initWidgetMeetingForm();
});

/* ---------- Виджет «Создание встречи» ---------- */
function initWidgetMeetingForm() {
  const form = document.querySelector(".widget-form");
  if (!form) return;
  form.addEventListener("submit", function () {
    // окончание = начало + 1 час (поле end_time скрыто)
    const start = form.querySelector('[name="start_time"]').value;
    const endHidden = document.getElementById("wgEndTime");
    if (start && endHidden) {
      const [h, m] = start.split(":").map(Number);
      const end = new Date(2000, 0, 1, h + 1, m);
      endHidden.value =
        String(end.getHours()).padStart(2, "0") + ":" + String(end.getMinutes()).padStart(2, "0");
    }
  });
}

/* ---------- Мои дела (todo-чеклист) ---------- */
function initTasks() {
  const list = document.getElementById("taskList");
  if (!list) return;

  const addBtn = document.getElementById("taskAdd");
  const titleInput = document.getElementById("taskTitle");
  const dateInput = document.getElementById("taskDate");
  const errEl = document.getElementById("taskError");
  const emptyEl = document.getElementById("taskEmpty");

  // форма добавления есть только на странице «Мои дела» (не на дашборде)
  if (addBtn && titleInput) {
    function addTask() {
      const title = titleInput.value.trim();
      if (!title) { errEl.textContent = "Введите название"; return; }
      errEl.textContent = "";
      $.ajax({
        url: "/api/tasks",
        type: "POST",
        contentType: "application/json",
        data: JSON.stringify({ title: title, due_date: dateInput.value || null }),
        success: function (t) {
          list.insertAdjacentHTML("afterbegin", renderTask(t));
          titleInput.value = "";
          dateInput.value = "";
          titleInput.focus();
          if (emptyEl) emptyEl.classList.add("d-none");
        },
        error: function (xhr) {
          errEl.textContent = (xhr.responseJSON && xhr.responseJSON.error) || "Ошибка";
        },
      });
    }
    addBtn.addEventListener("click", addTask);
    titleInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") addTask();
    });
  }

  // делегирование: чекбокс и удаление (работает и на странице, и в виджете)
  list.addEventListener("change", function (e) {
    if (e.target.classList.contains("todo-check")) {
      const item = e.target.closest(".todo-item");
      $.post("/api/tasks/" + item.dataset.id + "/toggle", function (res) {
        item.classList.toggle("done", res.done);
      });
    }
  });
  list.addEventListener("click", function (e) {
    const del = e.target.closest(".todo-del");
    if (del) {
      const item = del.closest(".todo-item");
      $.ajax({
        url: "/api/tasks/" + item.dataset.id,
        type: "DELETE",
        success: function () {
          item.remove();
          if (emptyEl && !list.querySelector(".todo-item")) emptyEl.classList.remove("d-none");
        },
      });
    }
  });
}

function renderTask(t) {
  const due = t.due ? '<div class="text-muted small">' + t.due + "</div>" : "";
  return (
    '<div class="todo-item" data-id="' + t.id + '">' +
    '<input class="form-check-input todo-check" type="checkbox">' +
    '<span class="task-dot" style="background:' + t.color + '"></span>' +
    '<div class="flex-grow-1"><div class="todo-title">' + escapeHtml(t.title) + "</div>" + due + "</div>" +
    '<button class="btn-icon todo-del" title="Удалить"><i class="bi bi-trash"></i></button>' +
    "</div>"
  );
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

/* ---------- Тёмная тема ---------- */
function applyThemeIcon(theme) {
  const btn = document.getElementById("themeToggle");
  if (!btn) return;
  btn.querySelector("i").className = theme === "dark" ? "bi bi-sun" : "bi bi-moon-stars";
}

function setTheme(theme) {
  document.documentElement.setAttribute("data-bs-theme", theme);
  localStorage.setItem("meetplan_theme", theme);
  applyThemeIcon(theme);
}

function initThemeToggle() {
  const current = localStorage.getItem("meetplan_theme") || "light";
  applyThemeIcon(current);
  const btn = document.getElementById("themeToggle");
  if (btn) {
    btn.addEventListener("click", function () {
      const now = document.documentElement.getAttribute("data-bs-theme");
      setTheme(now === "dark" ? "light" : "dark");
    });
  }
  // переключатель на странице настроек (если есть)
  const sw = document.getElementById("themeSwitch");
  if (sw) {
    sw.checked = current === "dark";
    sw.addEventListener("change", function () {
      setTheme(sw.checked ? "dark" : "light");
    });
  }
}

/* ---------- Календарь ---------- */
function isMobile() {
  return window.matchMedia("(max-width: 767.98px)").matches;
}

function calHeight() {
  // высота, в которую строки растягиваются ровно — без прокрутки и пустот
  return isMobile() ? Math.max(window.innerHeight - 150, 520) : 660;
}

function rightToolbar() {
  // на телефоне «Неделя» = список (сетка из 7 колонок нечитаема)
  return isMobile()
    ? "addEvent timeGridDay,listWeek"
    : "addEvent dayGridMonth,timeGridWeek,timeGridDay";
}

/* компактный рендер события: время и заголовок — по строке с многоточием */
function renderEventContent(arg) {
  if (!arg.view.type.startsWith("timeGrid")) return;  // месяц/список — по умолчанию
  return {
    html:
      '<div class="ev-content">' +
      (arg.timeText ? '<div class="ev-time">' + arg.timeText + "</div>" : "") +
      '<div class="ev-title">' + escapeHtml(arg.event.title) + "</div>" +
      "</div>",
  };
}

function initCalendar(el) {
  calendar = new FullCalendar.Calendar(el, {
    locale: "ru",
    initialView: isMobile() ? "timeGridDay" : "timeGridWeek",
    headerToolbar: { left: "today prev,next", center: "title", right: rightToolbar() },
    customButtons: {
      addEvent: { text: "+ Событие", click: openNewEventModal },
    },
    buttonText: { today: "Сегодня", month: "Месяц", week: "Неделя", day: "День", listWeek: "Список" },
    slotMinTime: "07:00:00",
    slotMaxTime: "23:00:00",
    slotDuration: "01:00:00",
    slotLabelFormat: { hour: "2-digit", minute: "2-digit", hour12: false },
    expandRows: true,         // строки заполняют высоту — без пустот и прокрутки
    nowIndicator: true,
    allDaySlot: false,
    dayMaxEvents: true,
    height: calHeight(),
    // шапка дня: день недели сверху, число в кружке (кружок на «сегодня»).
    // Только для сеток времени; в месяце/списке — стандартная шапка.
    dayHeaderContent: function (arg) {
      if (!arg.view.type.startsWith("timeGrid")) return;
      const wd = arg.date.toLocaleDateString("ru-RU", { weekday: "short" });
      const num = arg.date.getDate();
      return {
        html:
          '<div class="fc-dayhead"><span class="wd">' + wd + "</span>" +
          '<span class="dnum' + (arg.isToday ? " today" : "") + '">' + num + "</span></div>",
      };
    },
    events: "/api/events",
    eventTimeFormat: { hour: "2-digit", minute: "2-digit", hour12: false },
    eventContent: renderEventContent,
    eventClick: function (info) {
      showEventDetails(info.event);
    },
  });
  calendar.render();

  // переключаем вид/высоту при смене размера окна
  let lastMobile = isMobile();
  window.addEventListener("resize", function () {
    calendar.setOption("height", calHeight());
    const now = isMobile();
    if (now !== lastMobile) {
      lastMobile = now;
      calendar.changeView(now ? "timeGridDay" : "timeGridWeek");
      calendar.setOption("headerToolbar", {
        left: "today prev,next", center: "title", right: rightToolbar(),
      });
    }
  });
}

/* ---------- Детали события ---------- */
function statusClass(type, statusId) {
  if (type === "personal") return "st-personal";
  if (statusId === 2) return "st-confirmed";
  if (statusId === 3) return "st-rejected";
  return "st-pending";
}

function showEventDetails(event) {
  activeEvent = event;
  const props = event.extendedProps;
  document.getElementById("evTitle").textContent = event.title;
  document.getElementById("evDesc").textContent = props.description || "Без описания";

  const fmt = { hour: "2-digit", minute: "2-digit" };
  const dateStr = event.start.toLocaleDateString("ru-RU");
  const timeStr = event.start.toLocaleTimeString("ru-RU", fmt) +
    (event.end ? " – " + event.end.toLocaleTimeString("ru-RU", fmt) : "");
  document.getElementById("evTime").textContent = dateStr + ", " + timeStr;

  const badge = document.getElementById("evStatus");
  badge.textContent = props.statusLabel || "";
  badge.className = "badge " + statusClass(props.type, props.statusId);

  // удалять можно только личные дела (свои)
  const delBtn = document.getElementById("evDelete");
  delBtn.style.display = props.type === "personal" ? "inline-block" : "none";

  // изменять можно свои события (личное дело или встречу, где ты создатель)
  const editBtn = document.getElementById("evEdit");
  if (props.isOwner) {
    editBtn.style.display = "inline-block";
    editBtn.href = (props.type === "personal" ? "/event/" : "/meeting/") + event.id + "/edit";
  } else {
    editBtn.style.display = "none";
  }

  new bootstrap.Modal(document.getElementById("eventModal")).show();
}

/* удаление события */
document.addEventListener("click", function (e) {
  if (e.target.closest("#evDelete") && activeEvent) {
    const id = activeEvent.id;
    $.ajax({
      url: "/api/events/" + id,
      type: "DELETE",
      success: function () {
        activeEvent.remove();
        bootstrap.Modal.getInstance(document.getElementById("eventModal")).hide();
      },
      error: function () { alert("Не удалось удалить событие"); },
    });
  }
});

/* ---------- Создание личного события (AJAX) ---------- */
function openNewEventModal() {
  const modalEl = document.getElementById("newEventModal");
  if (!modalEl) return;
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById("neDate").value = today;
  document.getElementById("neError").textContent = "";
  new bootstrap.Modal(modalEl).show();
}

function bindNewEventModal() {
  const modalEl = document.getElementById("newEventModal");
  if (!modalEl) return;

  document.getElementById("neSave").addEventListener("click", function () {
    const title = document.getElementById("neTitle").value.trim();
    const date = document.getElementById("neDate").value;
    const start = document.getElementById("neStart").value;
    const end = document.getElementById("neEnd").value;
    const err = document.getElementById("neError");

    if (!title || !date || !start || !end) {
      err.textContent = "Заполните все поля.";
      return;
    }
    $.ajax({
      url: "/api/events",
      type: "POST",
      contentType: "application/json",
      data: JSON.stringify({
        title: title,
        description: document.getElementById("neDesc").value,
        start: date + "T" + start,
        end: date + "T" + end,
      }),
      success: function () {
        bootstrap.Modal.getInstance(modalEl).hide();
        document.getElementById("neTitle").value = "";
        document.getElementById("neDesc").value = "";
        calendar.refetchEvents();
      },
      error: function (xhr) {
        err.textContent = (xhr.responseJSON && xhr.responseJSON.error) || "Ошибка сохранения.";
      },
    });
  });
}

/* ---------- Веб-уведомления (поллинг) ---------- */
const NOTIF_KEY = "meetplan_seen_requests";

function getSeen() {
  try { return JSON.parse(localStorage.getItem(NOTIF_KEY)) || []; }
  catch (e) { return []; }
}
function setSeen(ids) {
  localStorage.setItem(NOTIF_KEY, JSON.stringify(ids));
}

function startNotificationPolling() {
  // запрашиваем разрешение на браузерные уведомления (один раз)
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission();
  }
  pollNotifications();
  setInterval(pollNotifications, 15000); // каждые 15 секунд
}

function pollNotifications() {
  $.getJSON("/api/notifications", function (data) {
    updateBadges(data.count);
    const seen = getSeen();
    const currentIds = data.items.map((i) => i.id);

    data.items.forEach(function (item) {
      if (!seen.includes(item.id)) {
        notify("Новый запрос на встречу",
          item.from + " приглашает: «" + item.title + "» (" + item.when + ")");
      }
    });
    // сохраняем только ещё актуальные id, чтобы не копить мусор
    setSeen(currentIds);
  });
}

function updateBadges(count) {
  // бейдж-точка в шапке
  document.querySelectorAll(".topbar-actions .dot").forEach((el) => {
    if (count > 0) { el.textContent = count; el.style.display = ""; }
    else { el.style.display = "none"; }
  });
}

function notify(title, body) {
  // тост Bootstrap
  showToast(title, body);
  // браузерное (push-подобное) уведомление
  if ("Notification" in window && Notification.permission === "granted") {
    try { new Notification(title, { body: body, icon: "" }); } catch (e) {}
  }
}

function showToast(title, body) {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const el = document.createElement("div");
  el.className = "toast align-items-center border-0";
  el.setAttribute("role", "alert");
  el.innerHTML =
    '<div class="toast-header">' +
    '<i class="bi bi-bell-fill text-primary me-2"></i>' +
    '<strong class="me-auto">' + title + "</strong>" +
    '<button type="button" class="btn-close" data-bs-dismiss="toast"></button></div>' +
    '<div class="toast-body">' + body + "</div>";
  container.appendChild(el);
  const t = new bootstrap.Toast(el, { delay: 8000 });
  t.show();
  el.addEventListener("hidden.bs.toast", () => el.remove());
}

/* ---------- Ответ на запрос встречи (AJAX) ---------- */
function respondRequest(reqId, action) {
  $.ajax({
    url: "/api/requests/" + reqId + "/" + action,
    type: "POST",
    success: function (res) {
      const card = document.getElementById("req-" + reqId);
      if (!card) return;
      const badge = card.querySelector(".status-badge");
      badge.textContent = res.label;
      badge.className = "badge status-badge mt-1 " + (action === "confirm" ? "st-confirmed" : "st-rejected");
      const actions = card.querySelector(".request-actions");
      if (actions) actions.remove();
    },
    error: function () { alert("Не удалось обработать запрос"); },
  });
}
