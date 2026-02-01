import type { ExtractPropTypes, ExtractPublicPropTypes } from 'vue';
export type CalendarDateType = 'prev-month' | 'next-month' | 'prev-year' | 'next-year' | 'today';
export declare const calendarProps: {
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
};
export type CalendarProps = ExtractPropTypes<typeof calendarProps>;
export type CalendarPropsPublic = ExtractPublicPropTypes<typeof calendarProps>;
export declare const calendarEmits: {
    "update:modelValue": (value: Date) => boolean;
    input: (value: Date) => boolean;
};
export type CalendarEmits = typeof calendarEmits;
