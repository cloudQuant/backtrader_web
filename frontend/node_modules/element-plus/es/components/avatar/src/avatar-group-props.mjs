import { placements } from '@popperjs/core';
import { avatarProps } from './avatar.mjs';
import { buildProps, definePropType } from '../../../utils/vue/props/runtime.mjs';
import { useTooltipContentProps } from '../../tooltip/src/content.mjs';

const avatarGroupProps = buildProps({
  size: avatarProps.size,
  shape: avatarProps.shape,
  collapseAvatars: Boolean,
  collapseAvatarsTooltip: Boolean,
  maxCollapseAvatars: {
    type: Number,
    default: 1
  },
  effect: {
    type: definePropType(String),
    default: "light"
  },
  placement: {
    type: definePropType(String),
    values: placements,
    default: "top"
  },
  popperClass: useTooltipContentProps.popperClass,
  popperStyle: useTooltipContentProps.popperStyle,
  collapseClass: String,
  collapseStyle: {
    type: definePropType([String, Array, Object])
  }
});

export { avatarGroupProps };
//# sourceMappingURL=avatar-group-props.mjs.map
