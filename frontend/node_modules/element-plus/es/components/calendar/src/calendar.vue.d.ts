declare var __VLS_1: {
    date: string;
}, __VLS_47: {
    data: {
        isSelected: boolean;
        type: string;
        day: string;
        date: Date;
    };
}, __VLS_57: {
    data: {
        isSelected: boolean;
        type: string;
        day: string;
        date: Date;
    };
};
type __VLS_Slots = {} & {
    header?: (props: typeof __VLS_1) => any;
} & {
    'date-cell'?: (props: typeof __VLS_47) => any;
} & {
    'date-cell'?: (props: typeof __VLS_57) => any;
};
declare const __VLS_base: import("vue").DefineComponent<{
    readonly modelValue: {
        readonly type: import("vue").PropType<Date>;
        readonly required: false;
        readonly validator: ((val: unknown) => boolean) | undefined;
        __epPropKey: true;
    };
    readonly range: {
        readonly type: import("vue").PropType<[Date, Date]>;
        readonly required: false;
        readonly validator: ((val: unknown) => boolean) | undefined;
        __epPropKey: true;
    };
    readonly controllerType: import("element-plus/es/utils").EpPropFinalized<StringConstructor, "button" | "select", unknown, "button", boolean>;
    readonly formatter: {
        readonly type: import("vue").PropType<(value: number, type: "year" | "month") => string | number>;
        readonly required: false;
        readonly validator: ((val: unknown) => boolean) | undefined;
        __epPropKey: true;
    };
}, {
    /** @description currently selected date */
    selectedDay: import("vue").WritableComputedRef<import("dayjs").Dayjs | undefined>;
    /** @description select a specific date */
    pickDay: (day: import("dayjs").Dayjs) => void;
    /** @description select date */
    selectDate: (type: import("./calendar").CalendarDateType) => void;
    /** @description Calculate the validate date range according to the start and end dates */
    calculateValidatedDateRange: (startDayjs: import("dayjs").Dayjs, endDayjs: import("dayjs").Dayjs) => [import("dayjs").Dayjs, import("dayjs").Dayjs][];
}, unknown, {}, {}, import("vue").ComponentOptionsMixin, import("vue").ComponentOptionsMixin, {
    "update:modelValue": (value: Date) => void;
    input: (value: Date) => void;
}, string, import("vue").PublicProps, Readonly<import("vue").ExtractPropTypes<{
    readonly modelValue: {
        readonly type: import("vue").PropType<Date>;
        readonly required: false;
        readonly validator: ((val: unknown) => boolean) | undefined;
        __epPropKey: true;
    };
    readonly range: {
        readonly type: import("vue").PropType<[Date, Date]>;
        readonly required: false;
        readonly validator: ((val: unknown) => boolean) | undefined;
        __epPropKey: true;
    };
    readonly controllerType: import("element-plus/es/utils").EpPropFinalized<StringConstructor, "button" | "select", unknown, "button", boolean>;
    readonly formatter: {
        readonly type: import("vue").PropType<(value: number, type: "year" | "month") => string | number>;
        readonly required: false;
        readonly validator: ((val: unknown) => boolean) | undefined;
        __epPropKey: true;
    };
}>> & {
    "onUpdate:modelValue"?: ((value: Date) => any) | undefined;
    onInput?: ((value: Date) => any) | undefined;
}, {
    readonly controllerType: import("element-plus/es/utils").EpPropMergeType<StringConstructor, "button" | "select", unknown>;
}, {}>;
declare const __VLS_export: __VLS_WithSlots<typeof __VLS_base, __VLS_Slots>;
declare const _default: typeof __VLS_export;
export default _default;
type __VLS_WithSlots<T, S> = T & {
    new (): {
        $slots: S;
    };
};
