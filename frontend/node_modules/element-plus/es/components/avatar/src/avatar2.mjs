import { defineComponent, inject, ref, computed, watch, openBlock, createElementBlock, normalizeClass, normalizeStyle, createBlock, unref, withCtx, resolveDynamicComponent, renderSlot } from 'vue';
import { ElIcon } from '../../icon/index.mjs';
import { avatarProps, avatarEmits } from './avatar.mjs';
import { avatarGroupContextKey } from './constants.mjs';
import _export_sfc from '../../../_virtual/plugin-vue_export-helper.mjs';
import { useNamespace } from '../../../hooks/use-namespace/index.mjs';
import { isString } from '@vue/shared';
import { isNumber } from '../../../utils/types.mjs';
import { addUnit } from '../../../utils/dom/style.mjs';

const _hoisted_1 = ["src", "alt", "srcset"];
const _sfc_main = defineComponent({
  ...{
    name: "ElAvatar"
  },
  __name: "avatar",
  props: avatarProps,
  emits: avatarEmits,
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const avatarGroupContext = inject(avatarGroupContextKey, void 0);
    const ns = useNamespace("avatar");
    const hasLoadError = ref(false);
    const size = computed(() => {
      var _a;
      return (_a = props.size) != null ? _a : avatarGroupContext == null ? void 0 : avatarGroupContext.size;
    });
    const shape = computed(
      () => {
        var _a, _b;
        return (_b = (_a = props.shape) != null ? _a : avatarGroupContext == null ? void 0 : avatarGroupContext.shape) != null ? _b : "circle";
      }
    );
    const avatarClass = computed(() => {
      const { icon } = props;
      const classList = [ns.b()];
      if (isString(size.value))
        classList.push(ns.m(size.value));
      if (icon)
        classList.push(ns.m("icon"));
      if (shape.value)
        classList.push(ns.m(shape.value));
      return classList;
    });
    const sizeStyle = computed(() => {
      return isNumber(size.value) ? ns.cssVarBlock({
        size: addUnit(size.value)
      }) : void 0;
    });
    const fitStyle = computed(() => ({
      objectFit: props.fit
    }));
    watch(
      () => props.src,
      () => hasLoadError.value = false
    );
    function handleError(e) {
      hasLoadError.value = true;
      emit("error", e);
    }
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock(
        "span",
        {
          class: normalizeClass(avatarClass.value),
          style: normalizeStyle(sizeStyle.value)
        },
        [
          (_ctx.src || _ctx.srcSet) && !hasLoadError.value ? (openBlock(), createElementBlock("img", {
            key: 0,
            src: _ctx.src,
            alt: _ctx.alt,
            srcset: _ctx.srcSet,
            style: normalizeStyle(fitStyle.value),
            onError: handleError
          }, null, 44, _hoisted_1)) : _ctx.icon ? (openBlock(), createBlock(unref(ElIcon), { key: 1 }, {
            default: withCtx(() => [
              (openBlock(), createBlock(resolveDynamicComponent(_ctx.icon)))
            ]),
            _: 1
          })) : renderSlot(_ctx.$slots, "default", { key: 2 })
        ],
        6
      );
    };
  }
});
var Avatar = /* @__PURE__ */ _export_sfc(_sfc_main, [["__file", "/home/runner/work/element-plus/element-plus/packages/components/avatar/src/avatar.vue"]]);

export { Avatar as default };
//# sourceMappingURL=avatar2.mjs.map
