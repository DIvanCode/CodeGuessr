export const totalShare = shares => Object.values(shares).reduce((total, share) => total + share, 0);

export function maxShare(shares, language) {
  return 100 - Object.keys(shares).filter(name => name !== language).length;
}

export function setShare(shares, language, percent) {
  const next = { ...shares, [language]: Math.min(percent, maxShare(shares, language)) };
  let excess = totalShare(next) - 100;
  const donors = Object.keys(shares)
    .filter(name => name !== language)
    .sort((a, b) => shares[b] - shares[a]);

  for (const donor of donors) {
    if (excess <= 0) break;
    const taken = Math.min(excess, next[donor] - 1);
    next[donor] -= taken;
    excess -= taken;
  }
  return next;
}
