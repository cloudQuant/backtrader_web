import dayjs from 'dayjs';
declare const __VLS_export: import("vue").DefineComponent<{
    readonly date: {
        readonly type: import("vue").PropType<dayjs.Dayjs>;
        readonly required: true;
        readonly validator: ((val: unknown) => boolean) | undefined;
        __epPropKey: true;
    };
    readonly formatter: {
        readonly type: import("vue").PropType<(value: number, type: "year" | "month") => string | number>;
        readonly required: false;
        readonly validator: ((val: unknown) => boolean) | undefined;
        __epPropKey: true;
    };
}, unknown, unknown, {}, {}, import("vue").ComponentOptionsMixin, import("vue").ComponentOptionsMixin, {
    "date-change": (date: "today" | dayjs.Dayjs) => void;
}, string, import("vue").PublicProps, Readonly<import("vue").ExtractPropTypes<{
    readonly date: {
        readonly type: import("vue").PropType<dayjs.Dayjs>;
        readonly required: true;
        readonly validator: ((val: unknown) => boolean) | undefined;
        __epPropKey: true;
    };
    readonly formatter: {
        readonly type: import("vue").PropType<(value: number, type: "year" | "month") => string | number>;
        readonly required: false;
        readonly validator: ((val: unknown) => boolean) | undefined;
        __epPropKey: true;
    };
}>> & {
    "onDate-change"?: ((date: "today" | dayjs.Dayjs) => any) | undefined;
}, {}, {}>;
declare const _default: typeof __VLS_export;
export default _default;
