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
  initMeetingCalendarLink();
  initMeetingConflictCheck();
  initMobileMeetingWidget();
});

/* ---------- Ссылка на календарь участника (форма встречи) ---------- */
function initMeetingCalendarLink() {
  const select = document.getElementById("meetingToUser");
  const link = document.getElementById("viewUserCalendarLink");
  if (!select || !link) return;
  function update() {
    const id = select.value;
    if (id) {
      link.href = "/users/" + id + "/calendar";
      link.classList.remove("d-none");
    } else {
      link.classList.add("d-none");
    }
  }
  select.addEventListener("change", update);
  update();
}

/* ---------- +1 час к времени (корректно через 23:00) ---------- */
function addOneHour(timeStr) {
  const parts = timeStr.split(":").map(Number);
  const d = new Date(2000, 0, 1, parts[0], parts[1] || 0);
  d.setHours(d.getHours() + 1);
  return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
}

function applyEndTimeFromStart(form, startSelector, endHiddenId) {
  const start = form.querySelector(startSelector);
  const endHidden = document.getElementById(endHiddenId);
  if (start && start.value && endHidden) {
    endHidden.value = addOneHour(start.value);
  }
}

/* ---------- Виджет «Создание встречи» ---------- */
function initWidgetMeetingForm() {
  const form = document.querySelector(".widget-form");
  if (!form) return;
  form.addEventListener("submit", function () {
    applyEndTimeFromStart(form, '[name="start_time"]', "wgEndTime");
  });
}

/* ---------- Мои дела (todo-чеклист) ---------- */
function initTasks() {
  const list = document.getElementById("taskList");
  if (!list) return;

  const addBtn = document.getElementById("taskAdd");
  const titleInput = document.getElementById("taskTitle");
  const dateInput = document.getElementById("taskDate");
  const timeInput = document.getElementById("taskTime");
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
        data: JSON.stringify({
          title: title,
          due_date: dateInput.value || null,
          due_time: timeInput && timeInput.value ? timeInput.value : null,
        }),
        success: function (t) {
          list.insertAdjacentHTML("afterbegin", renderTask(t));
          titleInput.value = "";
          dateInput.value = "";
          if (timeInput) timeInput.value = "";
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
    const editBtn = e.target.closest(".todo-edit");
    if (editBtn) {
      openTaskEdit(editBtn.closest(".todo-item"));
      return;
    }
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

  const editSave = document.getElementById("editTaskSave");
  if (editSave) {
    editSave.addEventListener("click", saveTaskEdit);
  }
}

let editingTaskItem = null;

function openTaskEdit(item) {
  editingTaskItem = item;
  document.getElementById("editTaskTitle").value = item.dataset.title || "";
  document.getElementById("editTaskDate").value = item.dataset.dueDate || "";
  document.getElementById("editTaskTime").value = item.dataset.dueTime || "";
  document.getElementById("editTaskError").textContent = "";
  new bootstrap.Modal(document.getElementById("taskEditModal")).show();
}

function saveTaskEdit() {
  if (!editingTaskItem) return;
  const title = document.getElementById("editTaskTitle").value.trim();
  const dueDate = document.getElementById("editTaskDate").value;
  const dueTime = document.getElementById("editTaskTime").value;
  const errEl = document.getElementById("editTaskError");
  if (!title) { errEl.textContent = "Введите название"; return; }
  $.ajax({
    url: "/api/tasks/" + editingTaskItem.dataset.id,
    type: "PUT",
    contentType: "application/json",
    data: JSON.stringify({
      title: title,
      due_date: dueDate || null,
      due_time: dueTime || null,
    }),
    success: function (res) {
      editingTaskItem.dataset.title = res.title;
      editingTaskItem.dataset.dueDate = dueDate;
      editingTaskItem.dataset.dueTime = dueTime;
      editingTaskItem.querySelector(".todo-title").textContent = res.title;
      const dueEl = editingTaskItem.querySelector(".todo-due");
      if (res.due) {
        dueEl.textContent = res.due;
        dueEl.classList.remove("d-none");
      } else {
        dueEl.classList.add("d-none");
      }
      bootstrap.Modal.getInstance(document.getElementById("taskEditModal")).hide();
    },
    error: function (xhr) {
      errEl.textContent = (xhr.responseJSON && xhr.responseJSON.error) || "Ошибка";
    },
  });
}

function renderTask(t) {
  const due = t.due ? '<div class="text-muted small todo-due">' + t.due + "</div>" : '<div class="text-muted small todo-due d-none"></div>';
  const dueDate = t.due_date || "";
  const dueTime = t.due_time || "";
  return (
    '<div class="todo-item" data-id="' + t.id + '" data-title="' + escapeHtml(t.title) + '" data-due-date="' + dueDate + '" data-due-time="' + dueTime + '">' +
    '<input class="form-check-input todo-check" type="checkbox">' +
    '<span class="task-dot" style="background:' + t.color + '"></span>' +
    '<div class="flex-grow-1"><div class="todo-title">' + escapeHtml(t.title) + "</div>" + due + "</div>" +
    '<button class="btn-icon todo-edit" title="Изменить"><i class="bi bi-pencil"></i></button>' +
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

function calHeight(viewType) {
  const vt = viewType || (calendar && calendar.view ? calendar.view.type : null);
  if (isMobile() && vt && vt.startsWith("list")) return "auto";
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
  if (arg.view.type.startsWith("list")) return renderListEventContent(arg);
  if (!arg.view.type.startsWith("timeGrid")) return;
  return {
    html:
      '<div class="ev-content">' +
      (arg.timeText ? '<div class="ev-time">' + arg.timeText + "</div>" : "") +
      '<div class="ev-title">' + escapeHtml(arg.event.title) + "</div>" +
      "</div>",
  };
}

/* карточка события для вида «Список» */
function formatListDate(date) {
  return date.toLocaleDateString("ru-RU", { weekday: "short", day: "numeric", month: "long" });
}

function formatListTimeRange(event) {
  const fmt = { hour: "2-digit", minute: "2-digit", hour12: false };
  if (!event.start) return "";
  const start = event.start.toLocaleTimeString("ru-RU", fmt);
  if (!event.end) return start;
  const end = event.end.toLocaleTimeString("ru-RU", fmt);
  return start + " – " + end;
}

function renderListEventContent(arg) {
  const props = arg.event.extendedProps;
  const statusLabel = props.statusLabel || "";
  const badge = statusLabel
    ? '<span class="list-ev-badge badge ' + statusClass(props.type, props.statusId) + '">' +
      escapeHtml(statusLabel) + "</span>"
    : "";
  const dateStr = arg.event.start ? formatListDate(arg.event.start) : "";
  const timeStr = formatListTimeRange(arg.event) || arg.timeText || "";
  const dateLine = dateStr
    ? '<div class="list-ev-date"><i class="bi bi-calendar3"></i> ' + dateStr + "</div>"
    : "";
  const timeLine = timeStr
    ? '<div class="list-ev-time"><i class="bi bi-clock"></i> ' + timeStr + "</div>"
    : "";
  return {
    html:
      '<div class="list-ev-card">' +
      dateLine +
      timeLine +
      '<div class="list-ev-title">' + escapeHtml(arg.event.title) + "</div>" +
      badge +
      "</div>",
  };
}

function initCalendar(el) {
  const eventsUrl = el.dataset.eventsUrl || "/api/events";
  const isReadOnly = eventsUrl !== "/api/events";
  const viewUserId = el.dataset.viewUserId || "";
  const tz = el.dataset.timezone || "local";
  calendar = new FullCalendar.Calendar(el, {
    locale: "ru",
    timeZone: tz,
    initialView: isMobile() ? "timeGridDay" : "timeGridWeek",
    headerToolbar: {
      left: "today prev,next",
      center: "title",
      right: isReadOnly ? rightToolbar().replace("addEvent ", "") : rightToolbar(),
    },
    customButtons: {
      addEvent: { text: "+ Событие", click: openNewEventModal },
    },
    buttonText: { today: "Сегодня", month: "Месяц", week: "Неделя", day: "День", listWeek: "Список" },
    views: {
      listWeek: {
        listDayFormat: { weekday: "long", day: "numeric", month: "long" },
        listDaySideFormat: false,
        noEventsContent: { html: '<div class="fc-list-empty">На этой неделе событий нет</div>' },
      },
    },
    slotMinTime: "07:00:00",
    slotMaxTime: "23:00:00",
    slotDuration: "01:00:00",
    slotLabelFormat: { hour: "2-digit", minute: "2-digit", hour12: false },
    expandRows: true,         // строки заполняют высоту — без пустот и прокрутки
    nowIndicator: true,
    allDaySlot: false,
    dayMaxEvents: true,
    height: calHeight(isMobile() ? "timeGridDay" : "timeGridWeek"),
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
    events: eventsUrl,
    eventTimeFormat: { hour: "2-digit", minute: "2-digit", hour12: false },
    eventContent: renderEventContent,
    eventDidMount: function (info) {
      if (!info.view.type.startsWith("list")) return;
      info.el.classList.add("list-ev-row");
      const accent = info.event.extendedProps.accent || info.event.borderColor || "#3b82f6";
      info.el.style.setProperty("--ev-accent", accent);
    },
    datesSet: function (info) {
      calendar.setOption("height", calHeight(info.view.type));
    },
    eventClick: function (info) {
      if (info.event.extendedProps.type === "task") {
        window.location.href = "/tasks";
        return;
      }
      showEventDetails(info.event);
    },
    editable: !isReadOnly,
    eventDrop: function (info) {
      reschedulePersonalEvent(info);
    },
    eventResize: function (info) {
      reschedulePersonalEvent(info);
    },
    dateClick: function (info) {
      if (!isReadOnly || !viewUserId) return;
      const d = info.date;
      const pad = (n) => String(n).padStart(2, "0");
      const date = d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
      const start = pad(d.getHours()) + ":" + pad(d.getMinutes());
      window.location.href = "/meeting/new?to=" + viewUserId + "&date=" + date + "&start=" + start;
    },
    selectable: isReadOnly,
  });
  calendar.render();

  // переключаем вид/высоту при смене размера окна
  let lastMobile = isMobile();
  window.addEventListener("resize", function () {
    calendar.setOption("height", calHeight(calendar.view.type));
    const now = isMobile();
    if (now !== lastMobile) {
      lastMobile = now;
      calendar.changeView(now ? "timeGridDay" : "timeGridWeek");
      calendar.setOption("headerToolbar", {
        left: "today prev,next",
        center: "title",
        right: isReadOnly ? rightToolbar().replace("addEvent ", "") : rightToolbar(),
      });
    }
  });
}

function reschedulePersonalEvent(info) {
  if (info.event.extendedProps.type !== "personal") {
    info.revert();
    return;
  }
  $.ajax({
    url: "/api/events/" + info.event.id + "/reschedule",
    type: "POST",
    contentType: "application/json",
    data: JSON.stringify({
      start: info.event.start.toISOString(),
      end: info.event.end.toISOString(),
    }),
    error: function () {
      info.revert();
      alert("Не удалось перенести событие");
    },
  });
}

/* ---------- Детали события ---------- */
function statusClass(type, statusId) {
  if (type === "personal" || type === "busy") return "st-personal";
  if (type === "task") return "st-task";
  if (statusId === 2) return "st-confirmed";
  if (statusId === 3) return "st-rejected";
  if (statusId === 4) return "st-cancelled";
  return "st-pending";
}

function showEventDetails(event) {
  activeEvent = event;
  const props = event.extendedProps;
  document.getElementById("evTitle").textContent = event.title;
  const descEl = document.getElementById("evDesc");
  if (props.type === "busy") {
    descEl.textContent = "Участник занят в это время.";
  } else if (props.type === "task") {
    descEl.textContent = "Задача из раздела «Мои дела». Нажмите, чтобы перейти к списку.";
  } else {
    descEl.textContent = props.description || "Без описания";
  }

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
  if (delBtn) delBtn.style.display = props.type === "personal" ? "inline-block" : "none";

  const editBtn = document.getElementById("evEdit");
  if (editBtn && props.isOwner && props.type !== "task") {
    editBtn.style.display = "inline-block";
    editBtn.href = (props.type === "personal" ? "/event/" : "/meeting/") + event.id + "/edit";
  } else if (editBtn) {
    editBtn.style.display = "none";
  }

  const cancelBtn = document.getElementById("evCancel");
  if (cancelBtn) {
    const canCancel = props.canCancel === true;
    cancelBtn.style.display = canCancel ? "inline-block" : "none";
    cancelBtn.dataset.eventId = event.id;
  }

  new bootstrap.Modal(document.getElementById("eventModal")).show();
}

/* удаление / отмена события */
document.addEventListener("click", function (e) {
  if (e.target.closest("#evDelete") && activeEvent) {
    const id = activeEvent.id;
    $.ajax({
      url: "/api/events/" + id,
      type: "DELETE",
      success: function () {
        activeEvent.remove();
        bootstrap.Modal.getInstance(document.getElementById("eventModal")).hide();
        if (calendar) calendar.refetchEvents();
      },
      error: function () { alert("Не удалось удалить событие"); },
    });
  }
  const cancelBtn = e.target.closest("#evCancel");
  if (cancelBtn && activeEvent) {
    if (!confirm("Отменить эту встречу?")) return;
    $.ajax({
      url: "/api/meetings/" + activeEvent.id + "/cancel",
      type: "POST",
      success: function () {
        bootstrap.Modal.getInstance(document.getElementById("eventModal")).hide();
        if (calendar) calendar.refetchEvents();
      },
      error: function () { alert("Не удалось отменить встречу"); },
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
        notifyRequest(item);
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

function notifyRequest(item) {
  showToast(
    "Новый запрос на встречу",
    item.from + " приглашает: «" + item.title + "» (" + item.when + ")",
    item.id
  );
  if ("Notification" in window && Notification.permission === "granted") {
    try { new Notification("Новый запрос на встречу", { body: item.from + ": " + item.title }); } catch (e) {}
  }
}

function showToast(title, body, reqId) {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const el = document.createElement("div");
  el.className = "toast align-items-center border-0";
  el.setAttribute("role", "alert");
  const actions = reqId
    ? '<div class="toast-actions mt-2 d-flex gap-2">' +
      '<button type="button" class="btn btn-success btn-sm" data-req-action="confirm" data-req-id="' + reqId + '">Принять</button>' +
      '<button type="button" class="btn btn-outline-danger btn-sm" data-req-action="reject" data-req-id="' + reqId + '">Отклонить</button>' +
      "</div>"
    : "";
  el.innerHTML =
    '<div class="toast-header">' +
    '<i class="bi bi-bell-fill text-primary me-2"></i>' +
    '<strong class="me-auto">' + title + "</strong>" +
    '<button type="button" class="btn-close" data-bs-dismiss="toast"></button></div>' +
    '<div class="toast-body">' + body + actions + "</div>";
  container.appendChild(el);
  const t = new bootstrap.Toast(el, { delay: 12000 });
  t.show();
  el.addEventListener("hidden.bs.toast", () => el.remove());
  el.querySelectorAll("[data-req-action]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      respondRequest(btn.dataset.reqId, btn.dataset.reqAction, true);
      t.hide();
    });
  });
}

function cancelMeeting(eventId) {
  if (!confirm("Отменить эту встречу?")) return;
  $.ajax({
    url: "/api/meetings/" + eventId + "/cancel",
    type: "POST",
    success: function () { location.reload(); },
    error: function () { alert("Не удалось отменить встречу"); },
  });
}

/* ---------- Ответ на запрос встречи (AJAX) ---------- */
function respondRequest(reqId, action, silent) {
  $.ajax({
    url: "/api/requests/" + reqId + "/" + action,
    type: "POST",
    success: function (res) {
      const card = document.getElementById("req-" + reqId);
      if (card) {
        const badge = card.querySelector(".status-badge");
        if (badge) {
          badge.textContent = res.label;
          badge.className = "badge status-badge mt-1 " + (action === "confirm" ? "st-confirmed" : "st-rejected");
        }
        const actions = card.querySelector(".request-actions");
        if (actions) actions.remove();
      }
      if (!silent) pollNotifications();
    },
    error: function () { alert("Не удалось обработать запрос"); },
  });
}

/* ---------- Проверка конфликтов (форма встречи) ---------- */
function initMeetingConflictCheck() {
  const form = document.querySelector("form.meeting-form");
  if (!form) return;
  const warn = document.getElementById("conflictWarn");
  const toUser = form.querySelector('[name="to_user"]');
  const date = form.querySelector('[name="date"]');
  const start = form.querySelector('[name="start_time"]');
  const end = form.querySelector('[name="end_time"]');
    const excludeId = form.dataset.excludeEventId;
    function check() {
    if (!toUser.value || !date.value || !start.value || !end.value) return;
    const startIso = date.value + "T" + start.value + ":00";
    const endIso = date.value + "T" + end.value + ":00";
    const payload = { to_user: toUser.value, start: startIso, end: endIso };
    if (excludeId) payload.exclude_event_id = excludeId;
    $.ajax({
      url: "/api/meetings/check-conflicts",
      type: "POST",
      contentType: "application/json",
      data: JSON.stringify(payload),
      success: function (res) {
        if (!warn) return;
        if (res.conflicts && res.conflicts.length) {
          const names = [...new Set(res.conflicts.map((c) => c.username))].join(", ");
          warn.textContent = "Конфликт расписания: " + names;
          warn.classList.remove("d-none");
        } else {
          warn.classList.add("d-none");
        }
      },
    });
  }
  [toUser, date, start, end].forEach(function (el) {
    if (el) el.addEventListener("change", check);
  });
  check();
}

/* ---------- Мобильный виджет встречи ---------- */
function initMobileMeetingWidget() {
  const form = document.getElementById("mobileMeetingForm");
  if (!form) return;
  form.addEventListener("submit", function () {
    applyEndTimeFromStart(form, '[name="start_time"]', "mobEndTime");
  });
}
