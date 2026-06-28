/* MeetPlan — клиентская логика (FullCalendar + jQuery AJAX) */

let calendar = null;
let activeEvent = null; // событие, открытое в модалке деталей

document.addEventListener("DOMContentLoaded", function () {
  initFriendsOnboarding();
  const el = document.getElementById("calendar");
  if (el) initCalendar(el);
  bindNewEventModal();
  startNotificationPolling();
  initThemeToggle();
  initTasks();
  initWidgetMeetingForms();
  initMeetingCalendarLink();
  initMeetingConflictCheck();
  initRequestsTabs();
});

/* ---------- Утилиты UI ---------- */
const FRIENDS_ONBOARDING_KEY = "meetplan_friends_onboarding_dismissed";

function friendsOnboardingStorageKey() {
  const uid = document.body.dataset.userId;
  return FRIENDS_ONBOARDING_KEY + (uid ? "_" + uid : "");
}

function dismissFriendsOnboarding() {
  try {
    localStorage.setItem(friendsOnboardingStorageKey(), "1");
  } catch (e) { /* private mode */ }
}

function isFriendsOnboardingDismissed() {
  try {
    return localStorage.getItem(friendsOnboardingStorageKey()) === "1";
  } catch (e) {
    return false;
  }
}

function initFriendsOnboarding() {
  if (document.body.dataset.markFriendsOnboarding) {
    dismissFriendsOnboarding();
  }
  const banner = document.getElementById("friendsOnboarding");
  if (!banner) return;
  if (isFriendsOnboardingDismissed()) {
    banner.remove();
    return;
  }
  const cta = banner.querySelector(".onboarding-dismiss-cta");
  if (cta) cta.addEventListener("click", dismissFriendsOnboarding);
  const closeBtn = banner.querySelector(".onboarding-dismiss-btn");
  if (closeBtn) {
    closeBtn.addEventListener("click", function () {
      dismissFriendsOnboarding();
      banner.remove();
    });
  }
}

function btnBusy(btn, busy, label) {
  if (!btn) return;
  if (busy) {
    if (!btn.dataset.origHtml) btn.dataset.origHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML =
      '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>' +
      (label || "Подождите…");
  } else {
    btn.disabled = false;
    if (btn.dataset.origHtml) btn.innerHTML = btn.dataset.origHtml;
  }
}

function hideCalendarSkeleton() {
  const sk = document.getElementById("calendarSkeleton");
  if (sk) sk.classList.add("is-hidden");
}

function showErrorToast(message) {
  showAppToast("Ошибка", message, "danger");
}

function showSuccessToast(message) {
  showAppToast("Готово", message, "success");
}

function showAppToast(title, body, variant) {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const icon = variant === "danger" ? "exclamation-triangle-fill text-danger"
    : variant === "success" ? "check-circle-fill text-success"
    : "info-circle-fill text-primary";
  const el = document.createElement("div");
  el.className = "toast align-items-center border-0";
  el.setAttribute("role", "alert");
  el.innerHTML =
    '<div class="toast-header">' +
    '<i class="bi bi-' + icon + ' me-2" aria-hidden="true"></i>' +
    '<strong class="me-auto">' + escapeHtml(title) + "</strong>" +
    '<button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Закрыть"></button></div>' +
    '<div class="toast-body">' + escapeHtml(body) + "</div>";
  container.appendChild(el);
  const t = new bootstrap.Toast(el, { delay: 6000 });
  t.show();
  el.addEventListener("hidden.bs.toast", function () { el.remove(); });
}

function confirmAction(options) {
  const opts = options || {};
  const modalEl = document.getElementById("confirmModal");
  if (!modalEl) return Promise.resolve(window.confirm(opts.message || opts.title || "Подтвердите действие"));
  const titleEl = document.getElementById("confirmModalTitle");
  const bodyEl = document.getElementById("confirmModalBody");
  const okBtn = document.getElementById("confirmModalOk");
  const cancelBtn = document.getElementById("confirmModalCancel");
  titleEl.textContent = opts.title || "Подтвердите действие";
  bodyEl.textContent = opts.message || "";
  okBtn.textContent = opts.confirmLabel || "Подтвердить";
  okBtn.className = "btn btn-sm " + (opts.confirmClass || "btn-primary");
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  return new Promise(function (resolve) {
    function cleanup() {
      okBtn.removeEventListener("click", onOk);
      modalEl.removeEventListener("hidden.bs.modal", onHide);
    }
    function onOk() {
      cleanup();
      done(true);
      modal.hide();
    }
    function onHide() {
      cleanup();
      done(false);
    }
    let settled = false;
    function done(val) {
      if (settled) return;
      settled = true;
      resolve(val);
    }
    okBtn.addEventListener("click", onOk);
    modalEl.addEventListener("hidden.bs.modal", onHide, { once: false });
    modal.show();
    cancelBtn.focus();
  });
}

/* ---------- Ссылка на календарь друга (форма встречи) ---------- */
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

/* ---------- Виджеты «Создание встречи» ---------- */
function initWidgetMeetingForms() {
  document.querySelectorAll(".widget-form, form.meeting-form").forEach(function (form) {
    const start = form.querySelector('[name="start_time"]');
    const end = form.querySelector('[name="end_time"]');
    if (start && end) {
      start.addEventListener("change", function () {
        if (start.value) end.value = addOneHour(start.value);
      });
    }
    form.addEventListener("submit", function () {
      if (start && end && start.value && !end.value) {
        end.value = addOneHour(start.value);
      }
    });
  });
}

/* ---------- Мои дела (todo-чеклист) ---------- */
function initTasks() {
  const lists = Array.from(document.querySelectorAll("#taskList, #taskListMobile"));
  if (!lists.length) return;

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
      btnBusy(addBtn, true, "Добавляем…");
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
          const html = renderTask(t);
          lists.forEach(function (list) { list.insertAdjacentHTML("afterbegin", html); });
          titleInput.value = "";
          dateInput.value = "";
          if (timeInput) timeInput.value = "";
          titleInput.focus();
          if (emptyEl) emptyEl.classList.add("d-none");
        },
        error: function (xhr) {
          errEl.textContent = (xhr.responseJSON && xhr.responseJSON.error) || "Ошибка";
        },
        complete: function () { btnBusy(addBtn, false); },
      });
    }
    addBtn.addEventListener("click", addTask);
    titleInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") addTask();
    });
  }

  function bindTaskList(list) {
    list.addEventListener("change", function (e) {
      if (e.target.classList.contains("todo-check")) {
        const checkbox = e.target;
        const item = checkbox.closest(".todo-item");
        const prev = checkbox.checked;
        checkbox.disabled = true;
        item.classList.add("is-loading");
        $.post("/api/tasks/" + item.dataset.id + "/toggle")
          .done(function (res) {
            item.classList.toggle("done", res.done);
          })
          .fail(function () {
            checkbox.checked = !prev;
            showErrorToast("Не удалось обновить дело");
          })
          .always(function () {
            checkbox.disabled = false;
            item.classList.remove("is-loading");
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
        const title = item.querySelector(".todo-title")?.textContent?.trim() || "это дело";
        confirmAction({
          title: "Удалить дело?",
          message: "«" + title + "» будет удалено без возможности восстановления.",
          confirmLabel: "Удалить",
          confirmClass: "btn-danger",
        }).then(function (ok) {
          if (!ok) return;
          btnBusy(del, true);
          $.ajax({
            url: "/api/tasks/" + item.dataset.id,
            type: "DELETE",
            success: function () {
              const id = item.dataset.id;
              lists.forEach(function (l) {
                l.querySelectorAll('.todo-item[data-id="' + id + '"]').forEach(function (el) { el.remove(); });
              });
              if (emptyEl && !document.getElementById("taskList")?.querySelector(".todo-item")) {
                emptyEl.classList.remove("d-none");
              }
              showSuccessToast("Дело удалено");
            },
            error: function () { showErrorToast("Не удалось удалить дело"); },
            complete: function () { btnBusy(del, false); },
          });
        });
      }
    });
  }
  lists.forEach(bindTaskList);

  const editSave = document.getElementById("editTaskSave");
  if (editSave) {
    editSave.addEventListener("click", function () {
      btnBusy(editSave, true, "Сохраняем…");
      saveTaskEdit(function () { btnBusy(editSave, false); });
    });
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

function saveTaskEdit(onComplete) {
  if (!editingTaskItem) {
    if (onComplete) onComplete();
    return;
  }
  const title = document.getElementById("editTaskTitle").value.trim();
  const dueDate = document.getElementById("editTaskDate").value;
  const dueTime = document.getElementById("editTaskTime").value;
  const errEl = document.getElementById("editTaskError");
  if (!title) { errEl.textContent = "Введите название"; if (onComplete) onComplete(); return; }
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
    complete: function () { if (onComplete) onComplete(); },
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

/* компактный рендер события: в месяце — одна строка «время · заголовок» */
function renderEventContent(arg) {
  if (arg.view.type.startsWith("list")) return renderListEventContent(arg);
  if (arg.view.type.startsWith("dayGrid")) {
    const time = monthEventTime(arg);
    const title = escapeHtml(arg.event.title);
    const line = time
      ? '<span class="ev-month-time">' + time + '</span><span class="ev-month-sep">·</span><span class="ev-month-title">' + title + "</span>"
      : '<span class="ev-month-title">' + title + "</span>";
    return { html: '<div class="ev-month">' + line + "</div>" };
  }
  if (!arg.view.type.startsWith("timeGrid")) return;
  const timeStr = formatListTimeRange(arg.event) || arg.timeText;
  return {
    html:
      '<div class="ev-content">' +
      (timeStr ? '<div class="ev-time">' + escapeHtml(timeStr) + "</div>" : "") +
      '<div class="ev-title">' + escapeHtml(arg.event.title) + "</div>" +
      "</div>",
  };
}

function monthEventTime(arg) {
  if (!arg.timeText) return "";
  const parts = arg.timeText.split(/\s*[–—-]\s*/);
  if (parts.length >= 2 && parts[0] === parts[1]) return parts[0];
  return parts[0];
}

/* карточка события для вида «Список» */
function calendarTz() {
  if (calendar) {
    const tz = calendar.getOption("timeZone");
    if (tz && tz !== "local") return tz;
  }
  const el = document.getElementById("calendar");
  return el ? calendarTimezoneFromEl(el) : undefined;
}

function formatInCalendarTz(date, options) {
  if (!date) return "";
  const tz = calendarTz();
  const opts = Object.assign({}, options);
  if (tz) opts.timeZone = tz;
  return new Intl.DateTimeFormat("ru-RU", opts).format(date);
}

function formatListDate(date) {
  return formatInCalendarTz(date, {
    weekday: "short",
    day: "numeric",
    month: "long",
  });
}

function formatListTimeRange(event) {
  if (!event.start) return "";
  const fmt = { hour: "2-digit", minute: "2-digit", hour12: false };
  const start = formatInCalendarTz(event.start, fmt);
  if (!event.end) return start;
  const end = formatInCalendarTz(event.end, fmt);
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

function calendarTimezoneFromEl(el) {
  const raw = (el && el.dataset.timezone || "").trim();
  return raw || "Europe/Moscow";
}

function initCalendar(el) {
  const eventsUrl = el.dataset.eventsUrl || "/api/events";
  const isReadOnly = eventsUrl !== "/api/events";
  const viewUserId = el.dataset.viewUserId || "";
  const tz = calendarTimezoneFromEl(el);
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
      dayGridMonth: { displayEventTime: false },
      dayGridDay: { displayEventTime: false },
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
    displayEventTime: false,
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
  hideCalendarSkeleton();
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
      showErrorToast("Не удалось перенести событие");
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
    descEl.textContent = "Задача из раздела «Мои дела». Можно удалить — она исчезнет и из списка дел.";
  } else {
    descEl.textContent = props.description || "Без описания";
  }

  const dateStr = formatInCalendarTz(event.start, { day: "2-digit", month: "2-digit", year: "numeric" });
  const timeFmt = { hour: "2-digit", minute: "2-digit", hour12: false };
  const timeStr = formatInCalendarTz(event.start, timeFmt) +
    (event.end ? " – " + formatInCalendarTz(event.end, timeFmt) : "");
  document.getElementById("evTime").textContent = dateStr + ", " + timeStr;

  const badge = document.getElementById("evStatus");
  badge.textContent = props.statusLabel || "";
  badge.className = "badge " + statusClass(props.type, props.statusId);

  // удаление: личные дела, встречи (полностью), задачи
  const delBtn = document.getElementById("evDelete");
  if (delBtn) {
    const canDelete =
      props.canDelete === true || props.type === "personal";
    delBtn.style.display = canDelete ? "inline-block" : "none";
    if (props.type === "meeting") {
      delBtn.innerHTML = '<i class="bi bi-trash"></i> Удалить встречу';
    } else if (props.type === "task") {
      delBtn.innerHTML = '<i class="bi bi-trash"></i> Удалить задачу';
    } else {
      delBtn.innerHTML = '<i class="bi bi-trash"></i> Удалить';
    }
  }

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
function deleteEventRequest(event) {
  const props = event.extendedProps;
  if (props.type === "task") return "/api/tasks/" + props.taskId;
  if (props.type === "meeting") return "/api/meetings/" + event.id;
  return "/api/events/" + event.id;
}

function deleteEventMessage(event) {
  const props = event.extendedProps;
  const title = event.title || "событие";
  if (props.type === "meeting") {
    return { title: "Удалить встречу?", message: "«" + title + "» будет удалена полностью у всех участников." };
  }
  if (props.type === "task") {
    return { title: "Удалить задачу?", message: "«" + title + "» будет удалена из календаря и списка дел." };
  }
  return { title: "Удалить событие?", message: "«" + title + "» будет удалено из календаря." };
}

document.addEventListener("click", function (e) {
  if (e.target.closest("#evDelete") && activeEvent) {
    const delBtn = e.target.closest("#evDelete");
    const id = activeEvent.id;
    const msg = deleteEventMessage(activeEvent);
    confirmAction({
      title: msg.title,
      message: msg.message,
      confirmLabel: "Удалить",
      confirmClass: "btn-danger",
    }).then(function (ok) {
      if (!ok) return;
      btnBusy(delBtn, true, "Удаляем…");
      $.ajax({
        url: deleteEventRequest(activeEvent),
        type: "DELETE",
        success: function () {
          activeEvent.remove();
          bootstrap.Modal.getInstance(document.getElementById("eventModal")).hide();
          if (calendar) calendar.refetchEvents();
          showSuccessToast("Удалено");
        },
        error: function () { showErrorToast("Не удалось удалить"); },
        complete: function () { btnBusy(delBtn, false); },
      });
    });
  }
  const cancelBtn = e.target.closest("#evCancel");
  if (cancelBtn && activeEvent) {
    confirmAction({
      title: "Отменить встречу?",
      message: "Участники увидят встречу как отменённую.",
      confirmLabel: "Отменить встречу",
      confirmClass: "btn-danger",
    }).then(function (ok) {
      if (!ok) return;
      btnBusy(cancelBtn, true, "Отменяем…");
      $.ajax({
        url: "/api/meetings/" + activeEvent.id + "/cancel",
        type: "POST",
        success: function () {
          bootstrap.Modal.getInstance(document.getElementById("eventModal")).hide();
          if (calendar) calendar.refetchEvents();
          showSuccessToast("Встреча отменена");
        },
        error: function () { showErrorToast("Не удалось отменить встречу"); },
        complete: function () { btnBusy(cancelBtn, false); },
      });
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
    const saveBtn = document.getElementById("neSave");
    const title = document.getElementById("neTitle").value.trim();
    const date = document.getElementById("neDate").value;
    const start = document.getElementById("neStart").value;
    const end = document.getElementById("neEnd").value;
    const err = document.getElementById("neError");

    if (!title || !date || !start || !end) {
      err.textContent = "Заполните все поля.";
      return;
    }
    btnBusy(saveBtn, true, "Сохраняем…");
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
      complete: function () { btnBusy(saveBtn, false); },
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
      '<button type="button" class="btn btn-success btn-sm" data-req-action="confirm" data-req-id="' + reqId + '">Подтвердить</button>' +
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

function cancelMeeting(eventId, btn) {
  confirmAction({
    title: "Отменить встречу?",
    message: "Участники увидят встречу как отменённую.",
    confirmLabel: "Отменить встречу",
    confirmClass: "btn-danger",
  }).then(function (ok) {
    if (!ok) return;
    btnBusy(btn, true, "Отменяем…");
    $.ajax({
      url: "/api/meetings/" + eventId + "/cancel",
      type: "POST",
      success: function () { location.reload(); },
      error: function () { showErrorToast("Не удалось отменить встречу"); btnBusy(btn, false); },
    });
  });
}

/* ---------- Ответ на запрос встречи (AJAX) ---------- */
function respondRequest(reqId, action, silent, btn) {
  if (btn) btnBusy(btn, true, action === "confirm" ? "Подтверждаем…" : "Отклоняем…");
  $.ajax({
    url: "/api/requests/" + reqId + "/" + action,
    type: "POST",
    success: function (res) {
      ["req-" + reqId, "req-mobile-" + reqId].forEach(function (cardId) {
        const card = document.getElementById(cardId);
        if (!card) return;
        const badge = card.querySelector(".status-badge");
        if (badge) {
          badge.textContent = res.label;
          badge.className = "badge status-badge mt-1 " + (action === "confirm" ? "st-confirmed" : "st-rejected");
        }
        const actions = card.querySelector(".request-actions");
        if (actions) actions.remove();
      });
      if (!silent) pollNotifications();
    },
    error: function () { showErrorToast("Не удалось обработать запрос"); },
    complete: function () { if (btn) btnBusy(btn, false); },
  });
}

/* ---------- Вкладки запросов (?tab=outgoing) ---------- */
function initRequestsTabs() {
  const tabs = document.getElementById("requestsTabs");
  if (!tabs) return;
  const params = new URLSearchParams(window.location.search);
  const tab = params.get("tab");
  if (tab === "outgoing") {
    const btn = tabs.querySelector('[data-bs-target="#outgoing"]');
    if (btn) bootstrap.Tab.getOrCreateInstance(btn).show();
  }
}

/* ---------- Проверка конфликтов (форма встречи и виджеты) ---------- */
function initMeetingConflictCheck() {
  document.querySelectorAll("form.meeting-form, form.widget-form").forEach(function (form) {
    const warn = form.querySelector("#conflictWarn") || form.querySelector(".widget-conflict-warn");
    const toUser = form.querySelector('[name="to_user"]');
    const date = form.querySelector('[name="date"]');
    const start = form.querySelector('[name="start_time"]');
    const end = form.querySelector('[name="end_time"]');
    const excludeId = form.dataset.excludeEventId;
    function check() {
      if (!toUser || !toUser.value || !date || !date.value || !start || !start.value || !end || !end.value) return;
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
    if (form.classList.contains("meeting-form")) check();
  });
}

/* initMobileMeetingWidget merged into initWidgetMeetingForms */
