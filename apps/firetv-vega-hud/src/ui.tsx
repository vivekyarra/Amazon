import React, {useState} from 'react';
import {Dimensions, Pressable, StyleSheet, Text, View} from 'react-native';

// Layout is authored for a 1920x1080 canvas and scaled to the device's logical
// window (the Vega Virtual Device reports 960x540 dp for a 1080p panel).
const SCALE = Math.max(0.3, Dimensions.get('window').width / 1920);
export const px = (n: number) => Math.round(n * SCALE * 10) / 10;

export const C = {
  bg: '#0B0F14',
  panel: '#151C25',
  panel2: '#1D2632',
  text: '#F4F7FA',
  dim: '#B7C2CF',
  focus: '#FFD23F',
  ok: '#4ADE80',
  bad: '#FF6B6B',
  warn: '#FBBF24',
  neutral: '#93C5FD',
};

export const toneColor = (t: string) =>
  t === 'ok' ? C.ok : t === 'bad' ? C.bad : t === 'warn' ? C.warn : C.neutral;

type BtnProps = {
  label: string;
  sub?: string;
  onPress?: () => void;
  preferred?: boolean;
  disabled?: boolean;
  danger?: boolean;
  testID?: string;
  style?: any;
  onFocusChange?: (f: boolean) => void;
  children?: React.ReactNode;
};

// Large D-pad target: thick yellow ring + "> " prefix when focused so focus is never
// conveyed by color alone.
export function FocusButton(p: BtnProps) {
  const [focused, setFocused] = useState(false);
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="button"
      accessibilityLabel={p.label + (p.sub ? '. ' + p.sub : '')}
      accessibilityState={{disabled: !!p.disabled}}
      hasTVPreferredFocus={!!p.preferred}
      focusable={true}
      onFocus={() => {
        setFocused(true);
        p.onFocusChange && p.onFocusChange(true);
      }}
      onBlur={() => {
        setFocused(false);
        p.onFocusChange && p.onFocusChange(false);
      }}
      onPress={() => {
        if (!p.disabled && p.onPress) {
          p.onPress();
        }
      }}
      style={[
        s.btn,
        p.danger && s.btnDanger,
        p.disabled && s.btnDisabled,
        focused && s.btnFocused,
        p.style,
      ]}>
      {p.children ? (
        <View>
          {p.children}
          {focused ? <Text style={s.focusTag}>FOCUSED - press OK</Text> : null}
        </View>
      ) : (
        <View>
          <Text style={[s.btnText, focused && s.btnTextFocused]}>
            {(focused ? '> ' : '') + p.label + (p.disabled ? ' (locked)' : '')}
          </Text>
          {p.sub ? <Text style={s.btnSub}>{p.sub}</Text> : null}
        </View>
      )}
    </Pressable>
  );
}

// On-screen D-pad keyboard. Works on any Vega device/simulator without relying on a
// system IME. A strict 5 x 10 grid of equal keys so Up/Down always keeps the column.
export const KEY_ROWS = [
  '1234567890'.split(''),
  'qwertyuiop'.split(''),
  'asdfghjkl-'.split(''),
  'zxcvbnm_./'.split(''),
  [':', '@', 'SHIFT', 'SPACE', 'DEL', 'CLEAR', '+', '!', '#', 'DONE'],
];

function Key({label, onPress, preferred}: {label: string; onPress: () => void; preferred?: boolean}) {
  const [focused, setFocused] = useState(false);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      hasTVPreferredFocus={!!preferred}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      onPress={onPress}
      style={[s.key, focused && s.keyFocused]}>
      <Text style={[label.length > 2 ? s.keyTextSmall : s.keyText, focused && s.btnTextFocused]}>{label}</Text>
    </Pressable>
  );
}

export function DpadKeyboard(p: {
  title: string;
  value: string;
  secure?: boolean;
  onChange: (v: string) => void;
  onDone: () => void;
}) {
  const [shift, setShift] = useState(false);
  const shown = p.secure ? p.value.replace(/./g, '*') : p.value;
  return (
    <View style={s.kb}>
      <Text style={s.kbTitle}>{p.title}</Text>
      <Text style={s.kbValue}>{shown || ' '}</Text>
      <Text style={s.btnSub}>
        {p.value.length} characters - SHIFT is {shift ? 'ON (UPPER CASE)' : 'off (lower case)'} - Back closes
      </Text>
      {KEY_ROWS.map((row, r) => {
        const cells: React.ReactNode[] = [];
        for (let c = 0; c < row.length; c++) {
          const k = row[c];
          const label = k.length === 1 && shift ? k.toUpperCase() : k;
          cells.push(
            <Key
              key={r + '-' + c}
              label={k === 'SHIFT' ? (shift ? 'SHIFT*' : 'SHIFT') : label}
              preferred={r === 0 && c === 0}
              onPress={() => {
                if (k === 'SHIFT') {
                  setShift(!shift);
                } else if (k === 'SPACE') {
                  p.onChange(p.value + ' ');
                } else if (k === 'DEL') {
                  p.onChange(p.value.slice(0, -1));
                } else if (k === 'CLEAR') {
                  p.onChange('');
                } else if (k === 'DONE') {
                  p.onDone();
                } else {
                  p.onChange(p.value + label);
                }
              }}
            />,
          );
        }
        return (
          <View key={'row' + r} style={s.kbRow}>
            {cells}
          </View>
        );
      })}
    </View>
  );
}

export function Badge({label, tone}: {label: string; tone: string}) {
  return (
    <View style={[s.badge, {borderColor: toneColor(tone)}]}>
      <Text style={[s.badgeText, {color: toneColor(tone)}]}>{label}</Text>
    </View>
  );
}

export function Row({k, v, mono}: {k: string; v: string; mono?: boolean}) {
  return (
    <View style={s.row}>
      <Text style={s.rowK}>{k}</Text>
      <Text style={[s.rowV, mono && s.mono]}>{v}</Text>
    </View>
  );
}

export const s = StyleSheet.create({
  btn: {
    minHeight: px(72),
    paddingVertical: px(14),
    paddingHorizontal: px(24),
    borderRadius: px(12),
    borderWidth: px(4),
    borderColor: '#334155',
    backgroundColor: C.panel2,
    justifyContent: 'center',
    margin: px(8),
  },
  btnFocused: {
    borderColor: C.focus,
    backgroundColor: '#2A3546',
    transform: [{scale: 1.03}],
  },
  btnDanger: {borderColor: '#7F1D1D'},
  btnDisabled: {opacity: 0.55},
  btnText: {color: C.text, fontSize: px(28), fontWeight: '700'},
  btnTextFocused: {color: C.focus},
  btnSub: {color: C.dim, fontSize: px(22), marginTop: px(4)},
  focusTag: {color: C.focus, fontSize: px(20), fontWeight: '700', marginTop: px(6)},
  badge: {
    borderWidth: px(3),
    borderRadius: px(8),
    paddingHorizontal: px(10),
    paddingVertical: px(2),
    alignSelf: 'flex-start',
    marginRight: px(10),
  },
  badgeText: {fontSize: px(22), fontWeight: '800'},
  row: {flexDirection: 'row', marginVertical: px(3)},
  rowK: {color: C.dim, fontSize: px(24), width: px(300)},
  rowV: {color: C.text, fontSize: px(24), flex: 1},
  mono: {fontFamily: 'monospace'},
  kb: {backgroundColor: C.panel, borderRadius: px(16), padding: px(24), width: px(1300)},
  kbTitle: {color: C.text, fontSize: px(34), fontWeight: '800'},
  kbValue: {
    color: C.text,
    fontSize: px(36),
    fontFamily: 'monospace',
    backgroundColor: C.panel2,
    padding: px(12),
    marginVertical: px(8),
    borderRadius: px(8),
  },
  kbRow: {flexDirection: 'row'},
  key: {
    width: px(112),
    height: px(76),
    margin: px(6),
    borderRadius: px(10),
    borderWidth: px(4),
    borderColor: '#334155',
    backgroundColor: C.panel2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  keyTextSmall: {color: C.text, fontSize: px(22), fontWeight: '800'},
  keyFocused: {borderColor: C.focus, backgroundColor: '#2A3546'},
  keyText: {color: C.text, fontSize: px(32), fontWeight: '800'},
});
