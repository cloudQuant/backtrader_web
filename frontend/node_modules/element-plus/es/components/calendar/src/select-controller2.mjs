import { defineComponent, computed, openBlock, createElementBlock, Fragment, createVNode, unref, normalizeClass, withCtx, createTextVNode, toDisplayString } from 'vue';
import dayjs from 'dayjs';
import { ElSelect } from '../../select/index.mjs';
import { ElButton } from '../../button/index.mjs';
import { selectControllerProps, selectControllerEmits } from './select-controller.mjs';
import _export_sfc from '../../../_virtual/plugin-vue_export-helper.mjs';
import { useNamespace } from '../../../hooks/use-namespace/index.mjs';
import { useLocale } from '../../../hooks/use-locale/index.mjs';
import { isFunction } from '@vue/shared';

const _sfc_main = defineComponent({
  ...{
    name: "SelectController"
  },
  __name: "select-controller",
  props: selectControllerProps,
  emits: selectControllerEmits,
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const nsSelect = useNamespace("calendar-select");
    const { t, lang } = useLocale();
    const monthOptions = Array.from({ length: 12 }, (_, index) => {
      const actualMonth = index + 1;
      const label = isFunction(props.formatter) ? props.formatter(actualMonth, "month") : actualMonth;
      return {
        value: actualMonth,
        label
      };
    });
    const yearValue = computed(() => props.date.year());
    const monthValue = computed(() => props.date.month() + 1);
    const yearOptions = computed(() => {
      const years = [];
      for (let i = -10; i < 10; i++) {
        const year = yearValue.value + i;
        if (year > 0) {
          const label = isFunction(props.formatter) ? props.formatter(year, "year") : year;
          years.push({ value: year, label });
        }
      }
      return years;
    });
    const handleYearChange = (year) => {
      emit(
        "date-change",
        dayjs(new Date(year, monthValue.value - 1, 1)).locale(lang.value)
      );
    };
    const handleMonthChange = (month) => {
      emit(
        "date-change",
        dayjs(new Date(yearValue.value, month - 1, 1)).locale(lang.value)
      );
    };
    const selectToday = () => {
      emit("date-change", "today");
    };
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock(
        Fragment,
        null,
        [
          createVNode(unref(ElSelect), {
            "model-value": yearValue.value,
            size: "small",
            class: normalizeClass(unref(nsSelect).e("year")),
            "validate-event": false,
            options: yearOptions.value,
            onChange: handleYearChange
          }, null, 8, ["model-value", "class", "options"]),
          createVNode(unref(ElSelect), {
            "model-value": monthValue.value,
            size: "small",
            class: normalizeClass(unref(nsSelect).e("month")),
            "validate-event": false,
            options: unref(monthOptions),
            onChange: handleMonthChange
          }, null, 8, ["model-value", "class", "options"]),
          createVNode(unref(ElButton), {
            size: "small",
            onClick: selectToday
          }, {
            default: withCtx(() => [
              createTextVNode(
                toDisplayString(unref(t)("el.datepicker.today")),
                1
              )
            ]),
            _: 1
          })
        ],
        64
      );
    };
  }
});
var SelectController = /* @__PURE__ */ _export_sfc(_sfc_main, [["__file", "/home/runner/work/element-plus/element-plus/packages/components/calendar/src/select-controller.vue"]]);

export { SelectController as default };
//# sourceMappingURL=select-controller2.mjs.map
