import Avatar from './src/avatar2.mjs';
import AvatarGroup from './src/avatar-group.mjs';
export { avatarEmits, avatarProps } from './src/avatar.mjs';
export { avatarGroupContextKey } from './src/constants.mjs';
export { avatarGroupProps } from './src/avatar-group-props.mjs';
import { withInstall, withNoopInstall } from '../../utils/vue/install.mjs';

const ElAvatar = withInstall(Avatar, {
  AvatarGroup
});
const ElAvatarGroup = withNoopInstall(AvatarGroup);

export { ElAvatar, ElAvatarGroup, ElAvatar as default };
//# sourceMappingURL=index.mjs.map
