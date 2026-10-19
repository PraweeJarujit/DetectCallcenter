/* แถวประวัติการตรวจ ใช้ทั้งหน้า "ตรวจ" และหน้า "ประวัติ" */
const SOURCE_META = {
  number_check: { icon: "phone", label: "ตรวจเบอร์" },
  text: { icon: "message", label: "ตรวจข้อความ" },
  audio: { icon: "mic", label: "ตรวจเสียง" },
  demo: { icon: "wave", label: "ทดลอง" },
};

function historyRow(log) {
  const meta = SOURCE_META[log.source] || SOURCE_META.number_check;
  const subject = log.phone_number ? formatPhone(log.phone_number) : meta.label;
  const extra = log.is_synthetic_voice ? " · พบเสียงสังเคราะห์" : "";
  return `<li>
    <span class="kind" title="${meta.label}">${icon(meta.icon)}</span>
    <div class="grow"><div class="title num">${escapeHtml(subject)}</div>
      <div class="sub">${log.phone_number ? meta.label + " · " : ""}${timeAgo(log.created_at)}${extra}</div></div>
    ${pill(log.status, log.status_label)}
  </li>`;
}
