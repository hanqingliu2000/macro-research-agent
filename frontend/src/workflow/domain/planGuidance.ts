export interface NormalizedPlanGuidance {
  blockers: string[];
  cautions: string[];
}

export function normalizePlanGuidance(
  unresolvedItems: string[],
  warnings: string[],
): NormalizedPlanGuidance {
  const blockers: string[] = [];
  const cautions = warnings
    .map((item) => item.trim())
    .filter((item) => item && !isAcquisitionDependentClaim(item.toLocaleLowerCase()));

  unresolvedItems.forEach((item) => {
    const text = item.trim();
    if (!text) return;
    const lowered = text.toLocaleLowerCase();
    if (isAcquisitionDependentClaim(lowered)) return;
    if (isExplicitlyNonBlocking(lowered)) {
      if (!isInternalDiscoveryNote(lowered)) cautions.push(text);
      return;
    }
    blockers.push(text);
  });

  return {
    blockers: unique(blockers),
    cautions: unique(
      cautions.filter((item) => {
        const lowered = item.toLocaleLowerCase();
        return !isInternalDiscoveryNote(lowered) && !lowered.startsWith("the previous ");
      }),
    ),
  };
}

function isAcquisitionDependentClaim(value: string) {
  if (
    [
      "connector",
      "attach a local file",
      "enable an executable",
      "api key",
      "credential",
      "连接器",
      "上传本地文件",
      "凭据",
    ].some((marker) => value.includes(marker))
  ) return false;

  return [
    "no reported values",
    "no observations",
    "missing years",
    "data gap",
    "estimation gap",
    "does not contain",
    "doesn't contain",
    "not available in",
    "unavailable in",
    "availability must be validated",
    "availability should be validated",
    "must be validated at acquisition",
    "must be validated during acquisition",
    "validate at acquisition",
    "validated at acquisition",
    "verify at acquisition",
    "confirmed at acquisition",
    "cannot be confirmed before acquisition",
    "exact codes must be validated",
    "coverage must be validated",
    "没有数据",
    "无数据",
    "缺少观测",
    "数据缺口",
    "缺失年份",
    "无法确认可用性",
    "获取时验证",
    "采集时验证",
  ].some((marker) => value.includes(marker));
}

function isExplicitlyNonBlocking(value: string) {
  return [
    "does not block",
    "doesn't block",
    "will not block",
    "non-blocking",
    "not a blocker",
    "不阻塞",
    "非阻塞",
    "不是阻塞项",
  ].some((marker) => value.includes(marker));
}

function isInternalDiscoveryNote(value: string) {
  if (
    value.includes("discovery index") &&
    ["cannot prove", "low-frequency", "bounded retrieval"].some((marker) =>
      value.includes(marker),
    )
  ) {
    return true;
  }
  return (
    value.includes("discovery-only") &&
    [
      "executable=false",
      "future connector admission",
      "not proposed",
      "not placed in data_sources",
      "blocked/alternative source",
    ].some((marker) => value.includes(marker))
  );
}

function unique(values: string[]) {
  return [...new Set(values)];
}
